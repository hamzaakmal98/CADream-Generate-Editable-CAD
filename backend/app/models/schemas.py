from pydantic import BaseModel
from typing import Optional


class ProjectInfo(BaseModel):
    project_name: str = "BESS Installation Project"
    client_name: str = ""
    location: str = ""
    system_capacity_kw: float = 380.0
    system_capacity_kwh: float = 760.0
    inverter_model: str = "Dynapower MPS-250"
    battery_model: str = "Gotion Edge 190"
    num_battery_units: int = 4
    num_inverters: int = 1


class BESSPlacement(BaseModel):
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    label: str = "BESS Unit"


class CablePath(BaseModel):
    points: list[dict]  # [{x, y}, ...]
    cable_type: str = "Power Cable"
    label: str = ""


class SLDComponent(BaseModel):
    component_type: str  # transformer, inverter, battery, meter, disconnect, panel, utility, pcc
    x: float
    y: float
    label: str = ""
    properties: dict = {}


class SLDConnection(BaseModel):
    from_id: str
    to_id: str
    points: list[dict] = []
    label: str = ""


class SitePlanData(BaseModel):
    bess_placements: list[BESSPlacement] = []
    cable_paths: list[CablePath] = []
    source_dxf_filename: Optional[str] = None


class SLDData(BaseModel):
    components: list[SLDComponent] = []
    connections: list[SLDConnection] = []


class GenerationRequest(BaseModel):
    project_info: ProjectInfo
    site_plan: SitePlanData
    sld: SLDData


class DXFLayerInfo(BaseModel):
    name: str
    color: int
    entity_count: int


class DXFParseResult(BaseModel):
    filename: str
    layers: list[DXFLayerInfo]
    bounds: dict  # {min_x, min_y, max_x, max_y}
    entity_count: int
    entities_json: list[dict]  # simplified entity data for frontend rendering
