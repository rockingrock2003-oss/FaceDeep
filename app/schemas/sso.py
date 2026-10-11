from pydantic import BaseModel


class SSOCallbackRequest(BaseModel):
    code: str
    redirect_uri: str
    state: str
