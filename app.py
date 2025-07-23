from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import subprocess
import tempfile
import logging
import io
import uuid
import time
import threading

# --- Basic Configuration ---
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
CORS(app)

# --- Temporary File Storage ---
# In a real production app, use a more robust cache like Redis or a scheduled job.
TEMP_FILE_CACHE = {}
CACHE_EXPIRATION_SECONDS = 3600  # 1 hour

# --- Health Check Route ---
@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"}), 200

# --- Helper function to map slider value to a specific DPI ---
def get_gs_resolution(quality_value):
    try:
        quality = int(quality_value)
    except (ValueError, TypeError):
        return 300 # Default to a high-quality 300 DPI
    dpi_map = {1: 72, 2: 96, 3: 120, 4: 150, 5: 200, 6: 250, 7: 300, 8: 400, 9: 500, 10: 600}
    return dpi_map.get(quality, 300)

# --- Ghostscript compression function ---
def run_ghostscript(input_path, output_path, resolution):
    command = [
        'gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
        '-dDownsampleColorImages=true', '-dDownsampleGrayImages=true', '-dDownsampleMonoImages=true',
        f'-dColorImageResolution={resolution}', f'-dGrayImageResolution={resolution}', f'-dMonoImageResolution={resolution}',
        '-dNOPAUSE', '-dQUIET', '-dBATCH', f'-sOutputFile={output_path}', input_path
    ]
    app.logger.info(f"Running GS with resolution: {resolution} DPI on {os.path.basename(input_path)}")
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)

# --- NEW: Initial Compression Route ---
@app.route('/compress-initial', methods=['POST'])
def compress_initial():
    app.logger.info("--- Received request for /compress-initial ---")
    if 'pdf' not in request.files:
        return jsonify({"error": "No PDF file part"}), 400
    
    pdf_file = request.files['pdf']
    
    # Create a temporary file to hold the original upload
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_original:
        pdf_file.stream.seek(0)
        temp_original.write(pdf_file.stream.read())
        original_path = temp_original.name

    # Create a path for the high-quality baseline file
    baseline_path = tempfile.mktemp(suffix=".pdf")
    file_id = str(uuid.uuid4())

    try:
        # Create the high-quality (300 DPI) baseline for future adjustments
        baseline_resolution = 300
        run_ghostscript(original_path, baseline_path, baseline_resolution)

        # Store the baseline file path in our cache
        TEMP_FILE_CACHE[file_id] = {'path': baseline_path, 'timestamp': time.time()}
        app.logger.info(f"Created baseline file for ID {file_id} at {baseline_path}")

        # Read the data to send back to the user for the first response
        with open(baseline_path, 'rb') as f:
            compressed_data = f.read()

        return jsonify({
            "message": "success",
            "file_id": file_id,
            "size": len(compressed_data)
        })

    except Exception as e:
        app.logger.error(f"Error in initial compression: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to create initial compressed file."}), 500
    finally:
        # Clean up the original uploaded temp file
        if os.path.exists(original_path):
            os.remove(original_path)

# --- NEW: Adjustment and Download Route ---
@app.route('/adjust-and-download', methods=['POST'])
def adjust_and_download():
    data = request.get_json()
    file_id = data.get('file_id')
    quality_value = data.get('quality', '7') # Default to 300 DPI
    app.logger.info(f"--- Received request for /adjust-and-download for ID {file_id} ---")

    if not file_id or file_id not in TEMP_FILE_CACHE:
        return jsonify({"error": "Invalid or expired file ID."}), 404

    baseline_path = TEMP_FILE_CACHE[file_id]['path']
    resolution = get_gs_resolution(quality_value)
    adjusted_path = tempfile.mktemp(suffix=".pdf")

    try:
        # Run GS on the baseline file with the new resolution
        run_ghostscript(baseline_path, adjusted_path, resolution)

        return send_file(
            adjusted_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'compressed-{resolution}dpi.pdf'
        )
    except Exception as e:
        app.logger.error(f"Error in adjustment compression: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to adjust file."}), 500
    finally:
        # The adjusted file is sent, so we can clean it up
        if os.path.exists(adjusted_path):
            os.remove(adjusted_path)

# --- NEW: Cache Cleanup ---
def cleanup_expired_files():
    while True:
        time.sleep(600) # Check every 10 minutes
        now = time.time()
        expired_ids = [
            file_id for file_id, data in TEMP_FILE_CACHE.items()
            if now - data['timestamp'] > CACHE_EXPIRATION_SECONDS
        ]
        if expired_ids:
            app.logger.info(f"Cleaning up {len(expired_ids)} expired files.")
            for file_id in expired_ids:
                file_path = TEMP_FILE_CACHE[file_id]['path']
                if os.path.exists(file_path):
                    os.remove(file_path)
                del TEMP_FILE_CACHE[file_id]

# --- Main entry point for the app ---
if __name__ == '__main__':
    # Start the cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_expired_files, daemon=True)
    cleanup_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
