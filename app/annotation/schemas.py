from pydantic import BaseModel, Field, model_validator


class RegionInput(BaseModel):
    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=1000)
    width: int = Field(gt=0, le=1000)
    height: int = Field(gt=0, le=1000)
    source: str = Field(default="MANUAL", max_length=30)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def inside_page(self) -> "RegionInput":
        if self.x + self.width > 1000 or self.y + self.height > 1000:
            raise ValueError("Region exceeds page bounds")
        return self


class RegionSet(BaseModel):
    regions: list[RegionInput] = Field(max_length=500)
