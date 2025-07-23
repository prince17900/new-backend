from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import subprocess
import tempfile
import logging
import io

# --- Basic Configuration ---
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
CORS(app)

# --- Health Check Route ---
@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"}), 200

# --- NEW: Helper function to map slider value to a specific DPI ---
def get_gs_resolution(quality_value):
    """
    Maps a 1-10 quality value to a specific DPI setting for image downsampling.
    """
    try:
        quality = int(quality_value)
    except (ValueError, TypeError):
        return 150 # Default to a balanced 150 DPI

    # This map provides a clear, granular control over the output resolution.
    dpi_map = {
        1: 72,   # Very Low (Screen quality)
        2: 96,
        3: 120,
        4: 150,  # Good balance (Ebook quality)
        5: 200,
        6: 250,
        7: 300,  # High quality (Printer quality)
        8: 400,
        9: 500,
        10: 600, # Highest quality (Prepress)
    }
    return dpi_map.get(quality, 150) # Default to 150 if value is out of range


# --- UPDATED: Ghostscript function now uses DPI for compression ---
def compress_with_ghostscript(input_stream, resolution):
    """
    Compresses a PDF by downsampling images to a specific resolution.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
        temp_input.write(input_stream.read())
        input_path = temp_input.name
    output_path = tempfile.mktemp(suffix=".pdf")
    try:
        # The -dPDFSETTINGS preset has been removed in favor of direct resolution control.
        command = [
            'gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            '-dDownsampleColorImages=true',
            '-dDownsampleGrayImages=true',
            '-dDownsampleMonoImages=true',
            f'-dColorImageResolution={resolution}',
            f'-dGrayImageResolution={resolution}',
            f'-dMonoImageResolution={resolution}',
            '-dNOPAUSE',
            '-dQUIET',
            '-dBATCH',
            f'-sOutputFile={output_path}',
            input_path
        ]
        app.logger.info(f"Running Ghostscript with resolution: {resolution} DPI")
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
        app.logger.info("Ghostscript compression successful.")
        with open(output_path, 'rb') as f:
            return f.read()
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)


# --- UPDATED: Flask route to use the new DPI logic ---
@app.route('/compress', methods=['POST'])
def compress_route():
    app.logger.info("--- Received request for /compress endpoint ---")
    try:
        if 'pdf' not in request.files:
            return jsonify({"error": "No PDF file part"}), 400
        
        pdf_file = request.files['pdf']
        # Set a default quality that corresponds to a balanced 150 DPI
        quality_value = request.form.get('quality', '4') 
        resolution = get_gs_resolution(quality_value)

        app.logger.info(f"File '{pdf_file.filename}' received. Compressing to {resolution} DPI.")
        compressed_pdf_data = compress_with_ghostscript(pdf_file.stream, resolution)

        if compressed_pdf_data is None:
            return jsonify({"error": "Compression failed to produce a file."}), 500
        
        app.logger.info("Successfully compressed file. Sending response.")
        return send_file(
            io.BytesIO(compressed_pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='compressed.pdf'
        )
    except Exception as e:
        app.logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred."}), 500

# --- Main entry point for the app ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
