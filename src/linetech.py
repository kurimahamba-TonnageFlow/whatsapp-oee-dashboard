"""LineTech configuration and validation. No separate downtime or job ledger."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FaultCategory(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    button_ids: list[int] = Field(default_factory=list, max_length=100)
    active: bool = True


class Equipment(StrictModel):
    machine_id: int = Field(gt=0)
    label: str = Field(min_length=1, max_length=80)
    categories: list[FaultCategory] = Field(default_factory=list, max_length=30)
    active: bool = True


class MachineGroup(StrictModel):
    key: Literal["sbs", "xray", "casepacker", "robot"]
    label: str = Field(min_length=1, max_length=80)
    equipment: list[Equipment] = Field(default_factory=list, max_length=20)


class PlannedReason(StrictModel):
    reason: str = Field(min_length=1, max_length=80)
    components: list[str] = Field(default_factory=list, max_length=20)
    active: bool = True


class LineTechConfig(StrictModel):
    enabled: bool = False
    groups: list[MachineGroup] = Field(default_factory=list, max_length=4)
    planned: list[PlannedReason] = Field(default_factory=list, max_length=30)
    products: list[str] = Field(default_factory=list, max_length=100)
    formats: list[str] = Field(default_factory=list, max_length=100)
    sizes: list[str] = Field(default_factory=list, max_length=100)
    product_engineering_required: bool = False

    @model_validator(mode="after")
    def unique_choices(self):
        if len({g.key for g in self.groups}) != len(self.groups):
            raise ValueError("Machine groups must be unique.")
        if self.enabled and {g.key for g in self.groups} != {"sbs", "xray", "casepacker", "robot"}:
            raise ValueError("Configure all four machine groups before enabling LineTech.")
        for values in [self.products, self.formats, self.sizes, [p.reason for p in self.planned]]:
            if len(set(values)) != len(values) or any(not v.strip() or len(v) > 120 for v in values):
                raise ValueError("Choices must be unique, nonblank and at most 120 characters.")
        from decimal import Decimal, InvalidOperation
        weights = set()
        for size in self.sizes:
            try:
                weight = Decimal(size)
                if not weight.is_finite() or weight <= 0:
                    raise ValueError("Pack sizes must be positive kilograms.")
                if weight in weights:
                    raise ValueError("Pack sizes must be distinct weights.")
                weights.add(weight)
            except InvalidOperation as error:
                raise ValueError("Pack sizes must be numeric kilograms.") from error
        for reason in self.planned:
            if reason.reason.casefold() == "changeover":
                raise ValueError("Changeover uses End Run, not a planned in-run stop.")
            if any(not v.strip() or len(v) > 40 for v in reason.components):
                raise ValueError("Component labels must be 1–40 characters.")
        for group in self.groups:
            for equipment in group.equipment:
                names = [c.name for c in equipment.categories]
                ids = [b for c in equipment.categories for b in c.button_ids]
                if len(set(names)) != len(names) or len(set(ids)) != len(ids):
                    raise ValueError("Each category and fault button must appear once per component.")
        return self


class ChangeoverSelection(StrictModel):
    kind: Literal["product", "format", "size"]
    next_value: str = Field(min_length=1, max_length=120)


def prepare_changeover(config, selection, previous):
    """Validate against current configuration; return an immutable intent snapshot."""
    settings = LineTechConfig.model_validate(config or {})
    choice = ChangeoverSelection.model_validate(selection)
    if not settings.enabled:
        raise ValueError("LineTech is not enabled on this line.")
    allowed = getattr(settings, {"product": "products", "format": "formats", "size": "sizes"}[choice.kind])
    if choice.next_value not in allowed:
        raise ValueError("Select a configured next product, format or size.")
    old = previous[{"product": "product", "format": "format", "size": "pack_weight_kg"}[choice.kind]]
    if choice.kind == "size":
        from decimal import Decimal, InvalidOperation
        try:
            size = Decimal(choice.next_value)
            if not size.is_finite() or size <= 0:
                raise ValueError("Configured sizes must be positive kilograms.")
            unchanged = old is not None and Decimal(str(old)) == size
        except InvalidOperation as error:
            raise ValueError("Configured sizes must be numeric kilograms.") from error
    else:
        unchanged = str(old) == choice.next_value
    if unchanged:
        raise ValueError("The next configuration must differ from the current one.")
    return {**choice.model_dump(), "previous_value": str(old) if old is not None else None,
            "engineering_required": choice.kind != "product" or settings.product_engineering_required,
            "qa_status": "awaiting_verification", "verification": None, "cancelled_at": None}


def validate_config_references(config, machines):
    """Management cannot reference another line's machines or fault buttons."""
    by_id = {m["id"]: m for m in machines}
    used = set()
    for group in config.groups:
        for equipment in group.equipment:
            machine = by_id.get(equipment.machine_id)
            if machine is None or equipment.machine_id in used:
                raise ValueError("Each component must reference one distinct machine on this line.")
            used.add(equipment.machine_id)
            valid = {b["id"] for b in machine["buttons"] if b["event_type"] == "unplanned_fault"}
            if any(b not in valid for c in equipment.categories for b in c.button_ids):
                raise ValueError("A category contains a fault button from another machine.")
