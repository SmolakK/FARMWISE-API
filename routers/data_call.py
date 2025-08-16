from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from schemas import ReadDataRequest, ReadDataResponse, User
from services import read_data
from api_utils import secure_filename
from fastapi.responses import FileResponse, StreamingResponse
import tempfile
import os
from logging_config import logger
from security import limiter, get_current_active_user
import asyncio
import json
from utils.email_utils import send_email
from dotenv import load_dotenv

api_router = APIRouter()


# Dependency to check for client disconnection
async def monitor_client_disconnection(request: Request, stop_event: asyncio.Event):
    """
    Continuously monitors client disconnection in a separate task.
    """
    try:
        while not await request.is_disconnected():
            if stop_event.is_set():
                return
            await asyncio.sleep(1)  # Check every second
    except asyncio.CancelledError:
        logger.warning("Client disconnected - request cancelled")
        raise HTTPException(status_code=499, detail="Client disconnected")
    logger.warning("Client disconnected")
    raise HTTPException(status_code=499, detail="Client disconnected")


# BACKGROUND PROCESS BACKUP
async def process_and_send_email(request_body, request, user_email):
    logger.info('Started processing background email task')
    try:
        boundingbox = getattr(request_body, 'bounding_box', None)
        countries = getattr(request_body, 'country', None)
        level = request_body.level
        time_from = request_body.time_from
        time_to = request_body.time_to
        factors = request_body.factors
        separate_api = getattr(request_body, 'separate_api', False)
        interpolation = getattr(request_body, 'interpolation', False)

        result = await read_data(
            bounding_box=boundingbox,
            country=countries,
            level=level,
            time_from=time_from,
            time_to=time_to,
            factors=factors,
            separate_api=separate_api,
            interpolation=interpolation
        )

        if not result:
            send_email(user_email, "Data Processing Failed", "No data available for the selected parameters.")
            return

        df = result['data']
        metadata = result['metadata']

        temp_dir = request.app.state.temp_dir

        # Save CSV
        data_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='w+', dir=temp_dir)
        df.to_csv(data_file.name, index=True)
        data_file.close()

        # Save metadata
        metadata_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='w+', dir=temp_dir)
        with open(metadata_file.name, 'w') as mf:
            json.dump(metadata, mf, indent=4)
        metadata_file.close()

        # Generate download links
        load_dotenv('public_host.env')
        base_url = os.getenv("PUBLIC_BASE_URL")
        data_download_link = f"{base_url}/download/{os.path.basename(data_file.name)}"
        metadata_download_link = f"{base_url}/download/{os.path.basename(metadata_file.name)}"

        # Send the email
        email_content = f"Your data file is ready for download:\n\nData File: {data_download_link}\nMetadata File: {metadata_download_link}"
        send_email(user_email, "Your Data is Ready", email_content)

    except Exception as e:
        logger.error(f"Error in background processing: {e}")
        send_email(user_email, "Data Processing Failed", "An internal error occurred during data processing.")


@api_router.post("/read-data")
@limiter.limit("5/minute")
async def read_data_endpoint(
        request_body: ReadDataRequest,
        request: Request,
        current_user: User = Depends(get_current_active_user)
                             ):
    """
    Endpoint to read data based on provided parameters and return a download link for the resulting CSV file.

    This endpoint accepts a request containing a bounding box, level, time range, and factors,
    processes the data, and generates a temporary CSV file, providing a link for downloading the file.

    :param request_body: An instance of ReadDataRequest containing parameters for reading data.
    :param request: The HTTP request object, used to generate the download link.
    :param current_user: The current authenticated user, retrieved through dependency injection.
    :raises HTTPException: Raises an error if there are issues during processing or file creation.
    :return: An instance of ReadDataResponse containing the download link for the generated CSV file.
    """
    try:
        logger.info('Started processing data')

        result = await read_data(
            bounding_box=getattr(request_body, 'bounding_box', None),
            country=getattr(request_body, 'country', None),
            level=request_body.level,
            time_from=request_body.time_from,
            time_to=request_body.time_to,
            factors=request_body.factors,
            separate_api=request_body.separate_api,
            interpolation=request_body.interpolation
        )

        if not result:
            logger.error("No data found for the selected parameters.")
            return {"status": "failure", "message": "No data available for the selected parameters."}

        df = result['data']
        metadata = result['metadata']

        temp_dir = request.app.state.temp_dir

        # Save CSV
        data_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='w+', dir=temp_dir)
        df.to_csv(data_file.name, index=True)
        data_file.close()

        # Save metadata
        metadata_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='w+', dir=temp_dir)
        with open(metadata_file.name, 'w') as mf:
            json.dump(metadata, mf, indent=4)
        metadata_file.close()

        # Generate download links

        base_url = str(request.base_url).replace("http://", "https://").rstrip('/')
        data_download_link = f"{base_url}/download/{os.path.basename(data_file.name)}"
        metadata_download_link = f"{base_url}/download/{os.path.basename(metadata_file.name)}"

        # Send the email
        email_content = (
            f"Your data file is ready for download:\n\n"
            f"Data File: {data_download_link}\n"
            f"Metadata File: {metadata_download_link}\n\n"
            f"Your request details:\n"
            f"- Time Range: {request_body.time_from} to {request_body.time_to}\n"
            f"- Level: {request_body.level}\n"
            f"- Factors: {', '.join(request_body.factors)}\n"
            f"- Location Mode: {'Country: ' + ', '.join(request_body.country) if hasattr(request_body, 'country') and request_body.country else 'Bounding Box: ' + str(request_body.bounding_box)}\n\n"
            f"DO NOT RESPOND TO THIS EMAIL\n"
        )
        send_email(current_user.email, "Your Data is Ready", email_content)

        # Return success response
        return "Data processing completed successfully. A download link has been sent to your email."

    except Exception as e:
        logger.error(f"Error in processing: {e}")
        return "ERROR: there was an error when processing your request. Try different parameters."


@api_router.get("/download/{file_name}")
async def download_file(file_name: str, background_tasks: BackgroundTasks, request: Request):
    """
    Downloads a file from the server after validating the filename to prevent directory traversal attacks.

    This endpoint ensures that the requested file exists in the server's temporary directory,
    and serves the file securely while scheduling its deletion after the response.

    :param file_name: The name of the file to download, as specified in the URL.
    :param background_tasks: BackgroundTasks to handle file deletion after the response is sent.
    :param request: The HTTP request object, used to access the application state.
    :param current_user: The current authenticated user, retrieved through dependency injection.
    :raises HTTPException: Raises an error if the file is not found or there is an unexpected error.
    :return: A FileResponse containing the requested file for download.
    """
    try:
        # Sanitize the file name to ensure it's secure
        safe_file_name = secure_filename(file_name)
        file_path = os.path.join(request.app.state.temp_dir, safe_file_name)

        # Ensure the file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        # Serve the file securely
        # background_tasks.add_task(os.unlink, file_path)
        return FileResponse(path=file_path, media_type='application/octet-stream', filename=safe_file_name)

    except ValueError as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
