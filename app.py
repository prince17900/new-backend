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

# --- UPDATED: Helper function with a new quality tier ---
def get_gs_quality_setting(quality_value):
    """
    Maps a numeric quality value (1-10) to a Ghostscript -dPDFSETTINGS preset.
    - /screen:      Low quality,      low size (72 dpi)
    - /ebook:       Medium quality,   medium size (150 dpi)
    - /printer:     High quality,     high size (300 dpi)
    - /prepress:    Very High quality, for professional printing (300-600 dpi)
    """
    try:
        quality = int(quality_value)
    except (ValueError, TypeError):
        return '/printer' # Default to high if value is invalid

    if quality <= 3:
        return '/screen'    # Low
    elif quality <= 6:
        return '/ebook'     # Medium
    elif quality <= 9:
        return '/printer'   # High
    else: # quality == 10
        return '/prepress'  # Very High (New Default)


# --- The Ghostscript compression function ---
def compress_with_ghostscript(input_stream, quality_setting):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
        temp_input.write(input_stream.read())
        input_path = temp_input.name
    output_path = tempfile.mktemp(suffix=".pdf")
    try:
        command = [
            'gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
            f'-dPDFSETTINGS={quality_setting}', '-dNOPAUSE', '-dQUIET',
            '-dBATCH', f'-sOutputFile={output_path}', input_path
        ]
        app.logger.info(f"Running Ghostscript command: {' '.join(command)}")
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
        app.logger.info("Ghostscript compression successful.")
        with open(output_path, 'rb') as f:
            return f.read()
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)


# --- Flask route with error handling ---
@app.route('/compress', methods=['POST'])
def compress_route():
    app.logger.info("--- Received request for /compress endpoint ---")
    try:
        if 'pdf' not in request.files:
            return jsonify({"error": "No PDF file part"}), 400
        pdf_file = request.files['pdf']
        quality_value = request.form.get('quality', '10') # Default to 10
        gs_setting = get_gs_quality_setting(quality_value)
        app.logger.info(f"File '{pdf_file.filename}' received. Compressing with setting: {gs_setting}")
        compressed_pdf_data = compress_with_ghostscript(pdf_file.stream, gs_setting)
        if compressed_pdf_data is None:
            return jsonify({"error": "Compression failed to produce a file."}), 500
        app.logger.info("Successfully compressed file. Sending response.")
        return send_file(
            io.BytesIO(compressed_pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='compressed.pdf'
        )
    except subprocess.TimeoutExpired:
        app.logger.error("Ghostscript command timed out.")
        return jsonify({"error": "Processing timed out. The file may be too large."}), 408
    except subprocess.CalledProcessError as e:
        app.logger.error(f"Ghostscript failed: {e.stderr}")
        return jsonify({"error": "Failed to process PDF with Ghostscript."}), 500
    except Exception as e:
        app.logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred."}), 500

# --- Main entry point for the app ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
