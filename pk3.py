import base64
import os

from dotenv import load_dotenv
from portkey_ai import Portkey

load_dotenv()

PORTKEY_API_KEY = os.getenv("PIPELEX_GATEWAY_API_KEY")

portkey = Portkey(api_key=PORTKEY_API_KEY, virtual_key="azure-9293")

with open("data/Job-Offer.pdf", "rb") as pdf_file:
    base64_pdf = base64.b64encode(pdf_file.read()).decode("utf-8")
doc_url = f"data:application/pdf;base64,{base64_pdf}"

response = portkey.post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    "/",
    model="mistral-document-ai-2505",
    document={"type": "document_url", "document_url": doc_url},
    include_image_base64=True,
)

print(response)
