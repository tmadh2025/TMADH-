#!/usr/bin/env python3
"""
TMADH Semantic Model Loader

Loads specification.yaml and creates a technology-neutral model
for JSON Schema, Avro, and Protobuf generators.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import yaml


@dataclass
class Field:
    """A field defined in the TMADH semantic specification."""

    id: str
    type: str
    required: bool = False
    values: Optional[List[str]] = None
    fields: List["Field"] = field(default_factory=list)
    items: Optional["Field"] = None
    additional_properties: bool = False


@dataclass
class SemanticModel:
    """Technology-neutral representation of specification.yaml."""

    specification: Dict[str, Any]
    fields: List[Field]
    required_fields: List[str]
    field_types: List[Dict[str, Any]]
    _path_map: Dict[str, Field] = field(default_factory=dict)

    def fields_by_path(self) -> Dict[str, Field]:
        """Return fields indexed by dot-separated paths."""
        if not self._path_map:
            self._build_path_map()
        return self._path_map

    def walk_fields(self) -> Generator[tuple[str, Field], None, None]:
        """Yield every field with its path."""
        yield from self.fields_by_path().items()

    def get_field(self, path: str) -> Optional[Field]:
        """Return a field by path, or None when it does not exist."""
        return self.fields_by_path().get(path)

    def _build_path_map(
        self,
        fields: Optional[List[Field]] = None,
        prefix: str = "",
    ) -> None:
        """Recursively build the field-path index."""
        if fields is None:
            fields = self.fields

        for model_field in fields:
            path = f"{prefix}.{model_field.id}" if prefix else model_field.id

            if path in self._path_map:
                raise ValueError(f"Duplicate field path: {path}")

            self._path_map[path] = model_field

            if model_field.fields:
                self._build_path_map(model_field.fields, path)

            if model_field.items and model_field.items.fields:
                self._build_path_map(
                    model_field.items.fields,
                    f"{path}[]",
                )


def _parse_fields(
    raw_fields: Any,
    parent_path: str = "",
) -> List[Field]:
    """Convert YAML field definitions into Field objects."""
    if raw_fields is None:
        return []

    if not isinstance(raw_fields, list):
        raise ValueError(
            f"'fields' under {parent_path or '<root>'} must be a list"
        )

    parsed_fields: List[Field] = []
    seen_ids = set()

    for raw in raw_fields:
        if not isinstance(raw, dict):
            raise ValueError(
                f"Field under {parent_path or '<root>'} must be an object"
            )

        field_id = raw.get("id")
        field_type = raw.get("type")

        if not field_id:
            raise ValueError(
                f"Missing field 'id' under {parent_path or '<root>'}"
            )

        if field_id in seen_ids:
            raise ValueError(
                f"Duplicate field id '{field_id}' "
                f"under {parent_path or '<root>'}"
            )

        if not field_type:
            raise ValueError(f"Missing type for field '{field_id}'")

        seen_ids.add(field_id)

        current_path = (
            f"{parent_path}.{field_id}"
            if parent_path
            else field_id
        )

        model_field = Field(
            id=field_id,
            type=field_type,
            required=bool(raw.get("required", False)),
            values=raw.get("values"),
            additional_properties=bool(
                raw.get("additional_properties", False)
            ),
        )

        if "fields" in raw:
            model_field.fields = _parse_fields(
                raw.get("fields"),
                current_path,
            )

        if "items" in raw:
            item_raw = raw.get("items")

            if not isinstance(item_raw, dict):
                raise ValueError(
                    f"'items' for '{current_path}' must be an object"
                )

            item_type = item_raw.get("type")

            if not item_type:
                raise ValueError(
                    f"Missing item type for array '{current_path}'"
                )

            item_field = Field(
                id=item_raw.get("id", "item"),
                type=item_type,
                required=bool(item_raw.get("required", False)),
                values=item_raw.get("values"),
                additional_properties=bool(
                    item_raw.get("additional_properties", False)
                ),
            )

            if "fields" in item_raw:
                item_field.fields = _parse_fields(
                    item_raw.get("fields"),
                    f"{current_path}[]",
                )

            model_field.items = item_field

        parsed_fields.append(model_field)

    return parsed_fields


def load_baseline(
    yaml_path: str = "specification.yaml",
) -> SemanticModel:
    """Load specification.yaml and return a SemanticModel."""
    path = Path(yaml_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Specification file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError("The YAML root must be an object")

    specification = data.get("specification")

    if not isinstance(specification, dict):
        raise ValueError(
            "Missing or invalid 'specification' key in YAML"
        )

    fields = _parse_fields(
        specification.get("fields", [])
    )

    validation = data.get("validation", {})

    if validation is None:
        validation = {}

    if not isinstance(validation, dict):
        raise ValueError("'validation' must be an object")

    constraints = validation.get(
        "structural_constraints",
        {},
    )

    if constraints is None:
        constraints = {}

    if not isinstance(constraints, dict):
        raise ValueError(
            "'validation.structural_constraints' must be an object"
        )

    required_fields = constraints.get(
        "required_fields",
        [],
    )
    field_types = constraints.get(
        "field_types",
        [],
    )

    if not isinstance(required_fields, list):
        raise ValueError("'required_fields' must be a list")

    if not isinstance(field_types, list):
        raise ValueError("'field_types' must be a list")

    model = SemanticModel(
        specification=specification,
        fields=fields,
        required_fields=required_fields,
        field_types=field_types,
    )

    model._build_path_map()
    return model


def main() -> int:
    """Run a basic semantic-model loading check."""
    try:
        model = load_baseline()

        print("Semantic model loaded successfully.")
        print(
            "Specification version:",
            model.specification.get("version", "unknown"),
        )
        print(
            "Specification status:",
            model.specification
            .get("metadata", {})
            .get("status", "unknown"),
        )
        print(
            "Operations:",
            ", ".join(
                model.specification.get("operations", [])
            ),
        )
        print(
            "Total field paths:",
            len(model.fields_by_path()),
        )
        print(
            "Required fields:",
            len(model.required_fields),
        )

        return 0

    except Exception as error:
        print(
            f"Failed to load semantic model: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
