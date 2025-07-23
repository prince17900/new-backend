from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import subprocess
import tempfile
import logging

# --- Basic Configuration ---
app = Flask(__name__)
# Allow all origins for simplicity. For production, you might want to restrict this.
# e.g., CORS(app, resources={r"/compress": {"origins": ["https://compressfast.in", "http://127.0.0.1:5500"]}})
CORS(app) 
logging.basicConfig(level=logging.INFO)


# --- Helper function to map frontend quality to Ghostscript settings ---
def get_gs_quality_setting(quality_value):
    """
    Maps a numeric quality value (1-10 from your frontend) to a Ghostscript
    -dPDFSETTINGS preset.
    
    - /screen: Low quality, low size (72 dpi) - Good for max compression
    - /ebook: Medium quality, medium size (150 dpi)
    - /printer: High quality, large size (300 dpi)
    - /default: Similar to /printer, good for general use
    """
    try:
        quality = int(quality_value)
    except (ValueError, TypeError):
        return '/ebook' # Default to medium if value is invalid

    if quality <= 3:
        return '/screen'  # Low quality (max compression)
    elif quality <= 7:
        return '/ebook'   # Medium quality
    else:
        return '/printer' # High quality (less compression)


# --- The new PDF compression function using Ghostscript ---
def compress_with_ghostscript(input_stream, quality_setting):
    """
    Compresses a PDF using the Ghostscript command-line tool.
    This function creates temporary files to handle the input and output
    for the subprocess command.
    """
    # Create temporary files with .pdf extension so Ghostscript recognizes them
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
        temp_input.write(input_stream.read())
        input_path = temp_input.name

    output_path = tempfile.mktemp(suffix=".pdf")

    try:
        # --- This is the Ghostscript command ---
        # It takes an input file, sets the compatibility and quality, and specifies an output file.
        command = [
            'gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            f'-dPDFSETTINGS={quality_setting}',
            '-dNOPAUSE',
            '-dQUIET',
            '-dBATCH',
            f'-sOutputFile={output_path}',
            input_path
        ]
        
        app.logger.info(f"Running Ghostscript with command: {' '.join(command)}")
        
        # Execute the command
        subprocess.run(command, check=True, capture_output=True, text=True)
        
        app.logger.info("Ghostscript compression successful.")

        # Read the compressed file's data into memory
        with open(output_path, 'rb') as f:
            compressed_data = f.read()
        
        return compressed_data

    except subprocess.CalledProcessError as e:
        # Log errors if Ghostscript fails
        app.logger.error("Ghostscript failed to compress the PDF.")
        app.logger.error(f"Stderr: {e.stderr}")
        app.logger.error(f"Stdout: {e.stdout}")
        return None
    except FileNotFoundError:
        # This error means Ghostscript is not installed or not in the system's PATH
        app.logger.error("Ghostscript not found. Please ensure it is installed on the server.")
        return None
    finally:
        # Clean up the temporary files
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)


# --- Your updated Flask route ---
@app.route('/compress', methods=['POST'])
def compress_route():
    app.logger.info("Received request for /compress endpoint.")

    if 'pdf' not in request.files:
        app.logger.warning("No PDF file found in the request.")
        return jsonify({"error": "No PDF file part"}), 400

    pdf_file = request.files['pdf']
    if pdf_file.filename == '':
        app.logger.warning("No PDF file selected.")
        return jsonify({"error": "No selected file"}), 400

    # Get the quality value from the form (1-10)
    quality_value = request.form.get('quality', '5') # Default to 5 (medium)
    gs_setting = get_gs_quality_setting(quality_value)
    
    app.logger.info(f"Compressing with quality value: {quality_value} -> GS setting: {gs_setting}")

    # Compress the PDF using the new function
    compressed_pdf_data = compress_with_ghostscript(pdf_file.stream, gs_setting)

    if compressed_pdf_data is None:
        return jsonify({"error": "PDF compression failed on the server."}), 500

    # Send the compressed file back to the user
    return send_file(
        io.BytesIO(compressed_pdf_data),
        mimetype='application/pdf',
        as_attachment=True,
        download_name='compressed.pdf'
    )

# --- Main entry point for the app ---
if __name__ == '__main__':
    # Render will set the PORT environment variable.
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
