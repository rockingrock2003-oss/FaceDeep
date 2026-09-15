from pydantic import BaseModel


class SSOCallbackRequest(BaseModel):
    provider: str
    code: str
    redirect_uri: str
