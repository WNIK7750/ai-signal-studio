from pydantic import BaseModel, Field


class AgentPackSearchInput(BaseModel):
    pack_id: str = Field(default="ai-editor", min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=300)


class AgentPackSearchMatch(BaseModel):
    path: str
    excerpt: str


class AgentPackSearchResult(BaseModel):
    status: str = "completed"
    matches: list[AgentPackSearchMatch] = Field(default_factory=list)


class ArtifactSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=10, ge=1, le=30)


class ArtifactSearchMatch(BaseModel):
    artifact_id: str
    filename: str
    media_type: str
    excerpt: str


class ArtifactSearchResult(BaseModel):
    status: str = "completed"
    matches: list[ArtifactSearchMatch] = Field(default_factory=list)
