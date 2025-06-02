import os

import aiofiles
from mistralai import Mistral


async def upload_file_for_ocr(
    mistral_client: Mistral,
    file_path: str,
) -> str:
    """
    Upload a local file to Mistral.

    Args:
        pdf_path: Path to the local file to upload

    Returns:
        ID of the uploaded file
    """
    async with aiofiles.open(file_path, "rb") as file:  # type: ignore[reportUnknownMemberType]
        file_content = await file.read()

    uploaded_file = await mistral_client.files.upload_async(
        file={"file_name": os.path.basename(file_path), "content": file_content},
        purpose="ocr",
    )
    return uploaded_file.id
