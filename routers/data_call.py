from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from schemas import ReadDataRequest, ReadDataResponse, User
from services import read_data
from api_utils import secure_filename
from fastapi.responses import FileResponse
import tempfile
import os
from logging_config import logger
from security import limiter, get_current_active_user

api_router = APIRouter()


@api_router.post("/read-data", response_model=ReadDataResponse)
@limiter.limit("5/minute")
async def read_data_endpoint(request_body: ReadDataRequest, request: Request,
                             current_user: User = Depends(get_current_active_user)):
    try:
        # Convert the request model to the format expected by read_data function
        bounding_box = request_body.bounding_box
        level = request_body.level
        time_from = request_body.time_from
        time_to = request_body.time_to
        factors = request_body.factors

        # Call the read_data function
        df = read_data(bounding_box, level, time_from, time_to, factors)

        # Use the temporary directory from the application state
        temp_dir = request.app.state.temp_dir
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='w+', dir=temp_dir)

        df.to_csv(temp_file.name, index=True)

        # Generate download link
        download_link = f"{str(request.base_url).rstrip('/')}/download/{os.path.basename(temp_file.name)}"

        # Make sure to close the file
        temp_file.close()

        # Return the response with the download link
        return ReadDataResponse(download_link=download_link)
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@api_router.get("/download/{file_name}")
async def download_file(file_name: str, background_tasks: BackgroundTasks, request: Request,
                        current_user: User = Depends(get_current_active_user)):
    """
    Download a file from the server, ensuring the filename is safe and prevents directory traversal.
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
