from datetime import datetime

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    collection_type: str


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class CollectionRead(BaseModel):
    id: int
    name: str
    description: str | None
    collection_type: str
    total_items: int
    created_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CollectionItemCreate(BaseModel):
    job_id: int
    order_index: int = 0
    notes: str | None = None


class CollectionItemRead(BaseModel):
    id: int
    collection_id: int
    job_id: int
    order_index: int
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
