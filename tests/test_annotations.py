import pytest
from pydantic import ValidationError

from app.annotation.schemas import RegionInput, RegionSet


def test_region_input_accepts_normalized_box() -> None:
    region = RegionInput(x=10, y=20, width=300, height=400)
    assert region.x + region.width == 310


def test_region_input_rejects_box_outside_page() -> None:
    with pytest.raises(ValidationError):
        RegionInput(x=900, y=20, width=200, height=100)


def test_region_set_is_bounded() -> None:
    value = RegionSet(regions=[RegionInput(x=0, y=0, width=1000, height=1000)])
    assert len(value.regions) == 1
