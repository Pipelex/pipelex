import asyncio

from pipelex.core.stuffs.pdf_content import PDFContent
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline


async def run_screen_candidates():
    return await execute_pipeline(
        pipe_code="screen_candidates",
        inputs={
            "job_offer_pdf": PDFContent(url="job_offer_pdf_url"),
            "cv_pdfs": PDFContent(url="cv_pdfs_url"),
        },
    )


if __name__ == "__main__":
    # Initialize Pipelex
    Pipelex.make()

    # Run the pipeline
    result = asyncio.run(run_screen_candidates())
