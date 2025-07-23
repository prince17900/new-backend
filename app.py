from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import subprocess
import tempfile
import logging
import io

# --- Basic Configuration ---
app = Flask(__name__)
# Configure logging to be more verbose
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Allow all origins for simplicity during debugging.
CORS(app)

# --- NEW: Health Check Route ---
# This helps us verify that the server is running.
@app.route('/', methods=['GET'])
def health_check():
    app.logger.info("Health check endpoint was hit successfully.")
    return jsonify({"status": "ok", "message": "Server is running"}), 200


# --- Helper function to map frontend quality to Ghostscript settings ---
def get_gs_quality_setting(quality_value):
    try:
        quality = int(quality_value)
    except (ValueError, TypeError):
        return '/ebook' # Default to medium

    if quality <= 3:
        return '/screen'
    elif quality <= 7:
        return '/ebook'
    else:
        return '/printer'


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
        
        # Increased timeout to 5 minutes (300 seconds) for large files
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
        
        app.logger.info("Ghostscript compression successful.")
        with open(output_path, 'rb') as f:
            return f.read()

    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)


# --- Your updated Flask route with better error handling ---
@app.route('/compress', methods=['POST'])
def compress_route():
    # This log should ALWAYS appear if the request reaches the app
    app.logger.info("--- Received request for /compress endpoint ---")

    try:
        if 'pdf' not in request.files:
            app.logger.warning("Request is missing the 'pdf' file part.")
            return jsonify({"error": "No PDF file part"}), 400

        pdf_file = request.files['pdf']
        quality_value = request.form.get('quality', '5')
        gs_setting = get_gs_quality_setting(quality_value)
        
        app.logger.info(f"File '{pdf_file.filename}' received. Compressing with setting: {gs_setting}")

        compressed_pdf_data = compress_with_ghostscript(pdf_file.stream, gs_setting)

        if compressed_pdf_data is None:
             # This case should ideally not be hit due to the check=True in subprocess
            app.logger.error("Compression returned None, which indicates an issue.")
            return jsonify({"error": "Compression failed to produce a file."}), 500
        
        app.logger.info("Successfully compressed file. Sending response.")
        return send_file(
            io.BytesIO(compressed_pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='compressed.pdf'
        )

    except subprocess.TimeoutExpired:
        app.logger.error("Ghostscript command timed out. The PDF might be too large or complex.")
        return jsonify({"error": "Processing timed out. The file may be too large."}), 408

    except subprocess.CalledProcessError as e:
        app.logger.error("Ghostscript failed with an error.")
        app.logger.error(f"Ghostscript Stderr: {e.stderr}")
        return jsonify({"error": "Failed to process PDF with Ghostscript."}), 500

    except Exception as e:
        # Catch-all for any other unexpected errors
        app.logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred."}), 500


# --- Main entry point for the app ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
