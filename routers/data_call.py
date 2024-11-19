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


@api_router.post("/read-data", response_model=ReadDataResponse)
@limiter.limit("5/minute")
async def read_data_endpoint(
        request_body: ReadDataRequest,
        request: Request,
        background_tasks: BackgroundTasks,
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
    stop_event = asyncio.Event()

    # Add client disconnection monitor as a background task
    background_tasks.add_task(monitor_client_disconnection, request, stop_event)

    async def stream_progress():
        try:
            # Convert the request model to the format expected by read_data function
            bounding_box = request_body.bounding_box
            level = request_body.level
            time_from = request_body.time_from
            time_to = request_body.time_to
            factors = request_body.factors

            # New parameters from request_body, with default values if not specified
            separate_api = request_body.separate_api if hasattr(request_body, 'separate_api') else False
            interpolation = request_body.interpolation if hasattr(request_body, 'interpolation') else False

            yield "Starting data processing...\n\n"

            # Call the read_data function
            df = await read_data(bounding_box, level, time_from, time_to, factors,
                                 separate_api=separate_api, interpolation=interpolation
                                 )

            # Finalize the processing
            yield "Data processing completed. Generating CSV file...\n\n"

            # Use the temporary directory from the application state
            temp_dir = request.app.state.temp_dir
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='w+', dir=temp_dir)

            df.to_csv(temp_file.name, index=True)

            # Generate download link
            download_link = f"{str(request.base_url).rstrip('/')}/download/{os.path.basename(temp_file.name)}"

            # Make sure to close the file
            temp_file.close()

            yield f"Download link: {download_link}\n\n"

        except Exception as e:
            logger.error(f"Error processing request: {e}")
            raise HTTPException(status_code=500, detail="Internal Server Error")
        finally:
            # Signal that the main task is completed
            stop_event.set()

    return StreamingResponse(stream_progress(), media_type="text/plain")


@api_router.get("/download/{file_name}")
async def download_file(file_name: str, background_tasks: BackgroundTasks, request: Request,
                        current_user: User = Depends(get_current_active_user),
                        ):
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
        background_tasks.add_task(os.unlink, file_path)
        return FileResponse(path=file_path, media_type='application/octet-stream', filename=safe_file_name)

    except ValueError as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
