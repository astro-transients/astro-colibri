# GENERATED FILE - DO NOT EDIT.
# Copied verbatim from Colibri_v2/colibri_flask_api/app/api_folder/controller/filter.py
# by colibri_client/sync_api_filters.py. Change the API file, then re-run
# `python sync_api_filters.py` in colibri_client/.

from __future__ import annotations

import json
import logging
import traceback
from abc import ABC, abstractmethod

from .maps_specification import _try_parse_float, get_converted_field_value


class BaseFilter(ABC):
    """
    Abstract base class for filter objects.
    Filters are used to define and apply filters event

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active. Will always return false otherwise.
        default_state (bool): The boolean value which is returned when the filter is deactivated

    Methods:
        apply_filter(event): Abstract method to apply the filter to an event.
        create_from_dict(base_dict_filter): Static abstract method to create a filter from a dictionary.
        generate_dict(): Abstract method to generate a dictionary representation of the filter.
    """

    def __init__(self, activated, default_state=False):
        """Initialize a BaseFilter with the specified activation status.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            default_state (bool): The boolean value which is returned when the filter is deactivated
        """
        self.activated = activated
        self.default_state = default_state

    @abstractmethod
    def apply_filter(self, event):
        """Apply the filter to an event.

        This method should be implemented by concrete subclasses.

        Args:
            event (Voevent): The event to which the filter is applied.

        Returns:
            bool: True if the event passes the filter, False otherwise.
        """
        pass

    @staticmethod
    @abstractmethod
    def create_from_dict(base_dict_filter):
        """Create a filter object from a dictionary representation.

        This is a static abstract method that should be implemented by concrete subclasses.

        Args:
            base_dict_filter (dict): A dictionary representation of the filter.

        Returns:
            BaseFilter: An instance of the filter created from the dictionary.
        """

        if "type" not in base_dict_filter:
            raise MissingParameterSpecification("type", "unknown")

        if base_dict_filter["type"] == "AndSpecification":
            return AndFilter.create_from_dict(base_dict_filter)
        elif base_dict_filter["type"] == "OrSpecification":
            return OrFilter.create_from_dict(base_dict_filter)
        elif base_dict_filter["type"] == "NotSpecification":
            return NotFilter.create_from_dict(base_dict_filter)
        elif base_dict_filter["type"] == "FieldSpecification":
            return OperatorFilter.create_from_dict(base_dict_filter)
        elif base_dict_filter["type"] == "MaxAbsoluteDifferenceSpecification":
            return MaxAbsoluteDifferenceFilter.create_from_dict(base_dict_filter)
        elif base_dict_filter["type"] == "TrueSpecification":
            return TrueFilter.create_from_dict(base_dict_filter)
        elif base_dict_filter["type"] == "FalseSpecification":
            return FalseFilter.create_from_dict(base_dict_filter)
        elif base_dict_filter["type"] == "ArraySpecification":
            return ArrayFilter.create_from_dict(base_dict_filter)
        elif base_dict_filter["type"] == "ContainsSpecification":
            return ContainsFilter.create_from_dict(base_dict_filter)
        elif base_dict_filter["type"] == "NumericStringSpecification":
            return NumericStringFilter.create_from_dict(base_dict_filter)
        else:
            raise UnknownFilterSpecification(base_dict_filter["type"])

    @abstractmethod
    def generate_dict(self):
        """Generate a dictionary representation of the filter.

        This method should be implemented by concrete subclasses.

        Returns:
            dict: A dictionary representation of the filter.
        """
        pass


class TrueFilter(BaseFilter):
    """A filter that is always true

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated

    Methods:
        apply_filter(event): Apply the AND filter to an event.
        create_from_dict(base_dict_filter): Create class from a dictionary.
        generate_dict(): Generate a dictionary representation of the class.
    """

    def __init__(self, activated, default_state=False):
        """Initialize an TrueFilter with the specified activation status and sub-filters.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            default_state (bool): The boolean value which is returned when the filter is deactivated
        """
        super().__init__(activated, default_state)

    def apply_filter(self, event):
        """Apply the filter, will always return True if activated otherwise return False

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: always True if activated, otherwise the default_state
        """
        if self.activated:
            return True
        else:
            return self.default_state

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Create an TrueFilter from a dictionary representation.

        Args:
            base_dict_filter (dict): A dictionary representation of the TrueFilter.

        Returns:
            TrueFilter: An instance of the TrueFilter created from the dictionary.
        """
        if "isActivated" not in base_dict_filter:
            base_dict_filter["isActivated"] = True
        if "defaultState" not in base_dict_filter:
            base_dict_filter["defaultState"] = False

        return TrueFilter(
            activated=base_dict_filter["isActivated"],
            default_state=base_dict_filter["defaultState"],
        )

    def generate_dict(self):
        """Generate a dictionary representation of the TrueFilter.

        Returns:
            dict: A dictionary representation of the TrueFilter.
        """
        return {
            "type": "TrueSpecification",
            "isActivated": self.activated,
            "defaultState": self.default_state,
        }


class FalseFilter(BaseFilter):
    """A filter that is always false

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated

    Methods:
        apply_filter(event): Apply the AND filter to an event.
        create_from_dict(base_dict_filter): Create class from a dictionary.
        generate_dict(): Generate a dictionary representation of the class.
    """

    def __init__(self, activated, default_state=False):
        """Initialize an TrueFilter with the specified activation status and sub-filters.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            default_state (bool): The boolean value which is returned when the filter is deactivated
        """
        super().__init__(activated, default_state)

    def apply_filter(self, event):
        """Apply the filter, will always return True if activated otherwise return False

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: always True if activated, otherwise the default_state
        """
        if self.activated:
            return False
        else:
            return self.default_state

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Create an TrueFilter from a dictionary representation.

        Args:
            base_dict_filter (dict): A dictionary representation of the TrueFilter.

        Returns:
            TrueFilter: An instance of the TrueFilter created from the dictionary.
        """
        if "isActivated" not in base_dict_filter:
            base_dict_filter["isActivated"] = True
        if "defaultState" not in base_dict_filter:
            base_dict_filter["defaultState"] = False

        return FalseFilter(
            activated=base_dict_filter["isActivated"],
            default_state=base_dict_filter["defaultState"],
        )

    def generate_dict(self):
        """Generate a dictionary representation of the TrueFilter.

        Returns:
            dict: A dictionary representation of the TrueFilter.
        """
        return {
            "type": "FalseSpecification",
            "isActivated": self.activated,
            "defaultState": self.default_state,
        }


class AndFilter(BaseFilter):
    """A filter that represents a logical AND combination of sub-filters.

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated
        sub_filters (list): A list of BaseFilter to be combined with AND.

    Methods:
        apply_filter(event): Apply the AND filter to an event.
        create_from_dict(base_dict_filter): Create class from a dictionary.
        generate_dict(): Generate a dictionary representation of the class.
    """

    def __init__(self, activated, sub_filters, default_state=False):
        """Initialize an AndFilter with the specified activation status and sub-filters.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            default_state (bool): The boolean value which is returned when the filter is deactivated
            sub_filters (list): A list of BaseFilter to be combined with AND.
        """
        super().__init__(activated, default_state)
        self.sub_filters = sub_filters

        if len(self.sub_filters) < 1:
            raise EmptyFilterList("AndSpecification")

    def apply_filter(self, event):
        """Apply the AND filter to an event.

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: True if the event passes the AND filter, default_state otherwise.
        """

        if not self.activated:
            return self.default_state

        results = True
        for i in range(len(self.sub_filters)):
            if not results:
                break
            results &= self.sub_filters[i].apply_filter(event)
        return results

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Create an AndFilter from a dictionary representation.

        Args:
            base_dict_filter (dict): A dictionary representation of the AndFilter.

        Returns:
            AndFilter: An instance of the AndFilter created from the dictionary.
        """
        if "specs" not in base_dict_filter:
            raise MissingParameterSpecification("specs", "AndSpecification")
        if "isActivated" not in base_dict_filter:
            base_dict_filter["isActivated"] = True
        if "defaultState" not in base_dict_filter:
            base_dict_filter["defaultState"] = False

        return AndFilter(
            activated=base_dict_filter["isActivated"],
            default_state=base_dict_filter["defaultState"],
            sub_filters=[
                BaseFilter.create_from_dict(spec) for spec in base_dict_filter["specs"]
            ],
        )

    def generate_dict(self):
        """Generate a dictionary representation of the AndFilter.

        Returns:
            dict: A dictionary representation of the AndFilter.
        """
        return {
            "type": "AndSpecification",
            "isActivated": self.activated,
            "defaultState": self.default_state,
            "specs": [sub_filter.generate_dict() for sub_filter in self.sub_filters],
        }


class OrFilter(BaseFilter):
    """A filter that represents a logical OR combination of sub-filters.

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated
        sub_filters (list): A list of BaseFilter to be combined with OR.

    Methods:
        apply_filter(event): Apply the OR filter to an event.
        create_from_dict(base_dict_filter): Create an OrFilter from a dictionary.
        generate_dict(): Generate a dictionary representation of the OrFilter.
    """

    def __init__(self, activated, sub_filters, default_state=False):
        """Initialize an OrFilter with the specified activation status and sub-filters.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            default_state (bool): The boolean value which is returned when the filter is deactivated
            sub_filters (list): A list of BaseFilter to be combined with OR.
        """
        super().__init__(activated, default_state)
        self.sub_filters = sub_filters

        if len(self.sub_filters) < 1:
            raise EmptyFilterList("OrSpecification")

    def apply_filter(self, event):
        """Apply the OR filter to an event.

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: True if the event passes the OR filter, default_state otherwise.
        """
        if not self.activated:
            return self.default_state

        results = False
        for i in range(len(self.sub_filters)):
            if results:
                break
            results |= self.sub_filters[i].apply_filter(event)
        return results

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Create an OrFilter from a dictionary representation.

        Args:
            base_dict_filter (dict): A dictionary representation of the OrFilter.

        Returns:
            OrFilter: An instance of the OrFilter created from the dictionary.
        """

        if "specs" not in base_dict_filter:
            raise MissingParameterSpecification("specs", "OrSpecification")
        if "isActivated" not in base_dict_filter:
            base_dict_filter["isActivated"] = True
        if "defaultState" not in base_dict_filter:
            base_dict_filter["defaultState"] = False

        return OrFilter(
            activated=base_dict_filter["isActivated"],
            default_state=base_dict_filter["defaultState"],
            sub_filters=[
                BaseFilter.create_from_dict(spec) for spec in base_dict_filter["specs"]
            ],
        )

    def generate_dict(self):
        """Generate a dictionary representation of the OrFilter.

        Returns:
            dict: A dictionary representation of the OrFilter.
        """
        return {
            "type": "OrSpecification",
            "isActivated": self.activated,
            "default_state": self.default_state,
            "specs": [sub_filter.generate_dict() for sub_filter in self.sub_filters],
        }


class NotFilter(BaseFilter):
    """A filter that represents a logical NOT operation on a single sub-filter.

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated
        sub_filter (BaseFilter): The BaseFilter to be negated.

    Methods:
        apply_filter(event): Apply the NOT filter to an event.
        create_from_dict(base_dict_filter): Create a NotFilter from a dictionary.
        generate_dict(): Generate a dictionary representation of the NotFilter.
    """

    def __init__(self, activated, sub_filter, default_state=False):
        """Initialize a NotFilter with the specified activation status and sub-filter.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            default_state (bool): The boolean value which is returned when the filter is deactivated
            sub_filter (BaseFilter): The sub-filter to be negated.
        """
        super().__init__(activated, default_state)
        self.sub_filter = sub_filter

    def apply_filter(self, event):
        """Apply the NOT filter to an event.

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: True if the event passes the NOT filter, False otherwise.
        """
        if not self.activated:
            return self.default_state

        return not self.sub_filter.apply_filter(event)

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Create a NotFilter from a dictionary representation.

        Args:
            base_dict_filter (dict): A dictionary representation of the NotFilter.

        Returns:
            NotFilter: An instance of the NotFilter created from the dictionary.
        """
        if "spec" not in base_dict_filter:
            raise MissingParameterSpecification("spec", "NotSpecification")
        if "isActivated" not in base_dict_filter:
            base_dict_filter["isActivated"] = True
        if "defaultState" not in base_dict_filter:
            base_dict_filter["defaultState"] = False

        return NotFilter(
            activated=base_dict_filter["isActivated"],
            default_state=base_dict_filter["defaultState"],
            sub_filter=BaseFilter.create_from_dict(base_dict_filter["spec"]),
        )

    def generate_dict(self):
        """Generate a dictionary representation of the NotFilter.

        Returns:
            dict: A dictionary representation of the NotFilter.
        """
        return {
            "type": "NotSpecification",
            "isActivated": self.activated,
            "defaultState": self.default_state,
            "spec": self.sub_filter.generate_dict(),
        }


class OperatorFilter(BaseFilter):
    """A filter that represents a comparison operation on a specific field of an event.

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated
        field_comparison (str): The field to be compared.
        type_field (str): The type of field to be compared.
        operator (str): The comparison operator (e.g., '==', '<', '>', '<=', '>=').
            array_index (int): In case the field is an array, the index on which to apply the value
        comparison_value: The value for the comparison.

    Methods:
        apply_filter(event): Apply the OperatorFilter to an event.
        create_from_dict(base_dict_filter): Create an OperatorFilter from a dictionary.
        generate_dict(): Generate a dictionary representation of the OperatorFilter.
    """

    def __init__(
        self,
        activated,
        field_comparison,
        type_field,
        operator,
        comparison_value,
        default_state=False,
        array_index=None,
    ):
        """Initialize an OperatorFilter with the specified activation status and parameters.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            default_state (bool): The boolean value which is returned when the filter is deactivated
            field_comparison (str): The field to be compared.
            type_field (str): The type of field to be compared.
            operator (str): The comparison operator (e.g., '==', '<', '>', '<=', '>=').
            array_index (int): In case the field is an array, the index on which to apply the value
            comparison_value: The value for the comparison.
        """

        super().__init__(activated, default_state)
        self.field_comparison = field_comparison
        self.type_field = type_field
        self.operator = operator
        self.comparison_value = comparison_value
        self.array_index = array_index

        if operator not in ["==", "!=", "<", "<=", ">", ">="]:
            raise UnknownOperatorFieldSpecification(operator)

        if type_field == "float":
            self.comparison_value = float(self.comparison_value)
        elif type_field == "array_float":
            self.comparison_value = float(self.comparison_value)
            if self.array_index is None:
                raise MissingArrayIndexSpecification(
                    self.field_comparison, "FieldSpecification"
                )
        elif type_field == "int" or type_field == "integer":
            self.type_field = "integer"
            self.comparison_value = int(self.comparison_value)
        elif type_field == "array_int" or type_field == "array_integer":
            self.comparison_value = int(self.comparison_value)
            self.type_field = "array_integer"
            if self.array_index is None:
                raise MissingArrayIndexSpecification(
                    self.field_comparison, "FieldSpecification"
                )
        elif type_field == "str" or type_field == "string":
            self.type_field = "string"
            self.comparison_value = str(self.comparison_value)

        elif type_field in [
            "maps_float",
            "maps_int",
            "maps_value_min",
            "maps_value_max",
            "maps_fast_rising_transient",
            "maps_fast_fading_transient",
            "date_range_difference",
            "maps_days_since_latest_date",
            "maps_days_since_earliest_date",
            "maps_days_since_peak_date",
        ]:
            self.type_field = type_field
            self.comparison_value = _try_parse_float(self.comparison_value)

        else:
            raise UnknownTypeValueSpecification(type_field, "FieldSpecification")

    def apply_filter(self, event):
        """Apply the OperatorFilter to an event.

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: True if the event passes the OperatorFilter, False otherwise.
        """
        if not self.activated:
            return self.default_state

        if self.type_field in [
            "maps_float",
            "maps_int",
            "maps_value_min",
            "maps_value_max",
            "maps_fast_rising_transient",
            "maps_fast_fading_transient",
            "date_range_difference",
            "maps_days_since_latest_date",
            "maps_days_since_earliest_date",
            "maps_days_since_peak_date",
        ]:
            if not isinstance(event, dict):
                # For pandas.Series, convert to dict
                event = event.to_dict()

            nested_value = get_converted_field_value(
                colibri_event=event,
                field_name=self.field_comparison,
                type_field=self.type_field,
                sep=".",
            )

            if nested_value is None:
                return False
            value_to_compare = nested_value

        else:
            try:
                if self.field_comparison in event:
                    # load parameter from event
                    value_to_compare = event[self.field_comparison]
                    if (
                        self.type_field == "array_integer"
                        or self.type_field == "array_float"
                    ):
                        # arrays are possibly retrieved as string => convert
                        if type(value_to_compare) is str:
                            value_to_compare = json.loads(event[self.field_comparison])[
                                self.array_index
                            ]
                        else:
                            value_to_compare = event[self.field_comparison][
                                self.array_index
                            ]
                else:  # fill default values for old events that do not contain all parameters
                    if self.type_field == "string":
                        value_to_compare = ""
                    else:
                        value_to_compare = -1.0
            # A missing key, a missing array index, or an array field that does
            # not parse (a few stored events hold a Python repr of the map
            # instead of JSON) all mean "no value to compare" => reject the
            # event, as the frontend does, rather than raise out of the filter.
            except (KeyError, IndexError, TypeError, ValueError):
                return False

        if self.operator == "==":
            if self.type_field == "string":
                if not isinstance(value_to_compare, str):
                    value_to_compare = str(value_to_compare)
                results = value_to_compare.lower() == self.comparison_value.lower()
            else:
                results = value_to_compare == self.comparison_value
        elif self.operator == "!=":
            if self.type_field == "string":
                if not isinstance(value_to_compare, str):
                    value_to_compare = str(value_to_compare)
                results = value_to_compare.lower() != self.comparison_value.lower()
            else:
                results = value_to_compare != self.comparison_value
        elif self.operator == ">":
            results = value_to_compare > self.comparison_value
        elif self.operator == ">=":
            results = value_to_compare >= self.comparison_value
        elif self.operator == "<":
            results = value_to_compare < self.comparison_value
        elif self.operator == "<=":
            results = value_to_compare <= self.comparison_value
        else:
            raise UnknownOperatorFieldSpecification(self.operator)
        return results

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Create an OperatorFilter from a dictionary representation.

        Args:
            base_dict_filter (dict): A dictionary representation of the OperatorFilter.

        Returns:
            OperatorFilter: An instance of the OperatorFilter created from the dictionary.
        """

        if "field" not in base_dict_filter:
            raise MissingParameterSpecification("field", "FieldSpecification")
        if "value" not in base_dict_filter:
            raise MissingParameterSpecification(
                "value", "FieldSpecification", name_field=base_dict_filter["field"]
            )
        if "operation" not in base_dict_filter:
            raise MissingParameterSpecification(
                "operation", "FieldSpecification", name_field=base_dict_filter["field"]
            )
        if "typeField" not in base_dict_filter:
            raise MissingParameterSpecification(
                "typeField", "FieldSpecification", name_field=base_dict_filter["field"]
            )
        if "isActivated" not in base_dict_filter:
            base_dict_filter["isActivated"] = True
        if "defaultState" not in base_dict_filter:
            base_dict_filter["defaultState"] = False
        if "arrayIndex" not in base_dict_filter:
            base_dict_filter["arrayIndex"] = None

        return OperatorFilter(
            activated=base_dict_filter["isActivated"],
            default_state=base_dict_filter["defaultState"],
            operator=base_dict_filter["operation"],
            field_comparison=base_dict_filter["field"],
            type_field=base_dict_filter["typeField"],
            array_index=base_dict_filter["arrayIndex"],
            comparison_value=base_dict_filter["value"],
        )

    def generate_dict(self):
        """Generate a dictionary representation of the OperatorFilter.

        Returns:
            dict: A dictionary representation of the OperatorFilter.
        """
        return {
            "type": "FieldSpecification",
            "isActivated": self.activated,
            "defaultState": self.default_state,
            "operation": self.operator,
            "field": self.field_comparison,
            "typeField": self.type_field,
            "arrayIndex": self.array_index,
            "value": self.comparison_value,
        }


class MaxAbsoluteDifferenceFilter(BaseFilter):
    """A filter that represents a range around a central value

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated
        field_comparison (str): The field to be compared.
        type_field (str): The type of field to be compared.
        central_value: The value at the center of the range.
        range: The range available on each side of the central value.

    Methods:
        apply_filter(event): Apply the OperatorFilter to an event.
        create_from_dict(base_dict_filter): Create an OperatorFilter from a dictionary.
        generate_dict(): Generate a dictionary representation of the OperatorFilter.
    """

    def __init__(
        self,
        activated,
        field_comparison,
        type_field,
        central_value,
        range,
        default_state=False,
    ):
        """Initialize an OperatorFilter with the specified activation status and parameters.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            default_state (bool): The boolean value which is returned when the filter is deactivated
            field_comparison (str): The field to be compared.
            type_field (str): The type of field to be compared.
            central_value: The value at the center of the range.
            range: The range available on each side of the central value.
        """

        super().__init__(activated, default_state)
        self.field_comparison = field_comparison
        self.type_field = type_field
        self.central_value = central_value
        self.range = range

        if type_field == "float":
            self.central_value = float(self.central_value)
        elif type_field == "int" or type_field == "integer":
            self.type_field = "integer"
            self.central_value = int(self.central_value)
        else:
            raise UnknownTypeValueSpecification(
                type_field, "MaxAbsoluteDifferenceSpecification"
            )

    def apply_filter(self, event):
        """Apply the OperatorFilter to an event.

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: True if the event passes the OperatorFilter, False otherwise.
        """
        if not self.activated:
            return self.default_state

        if self.field_comparison not in event:
            results = False
        else:
            results = (
                abs(event[self.field_comparison] - self.central_value) < self.range
            )
        return results

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Create an OperatorFilter from a dictionary representation.

        Args:
            base_dict_filter (dict): A dictionary representation of the OperatorFilter.

        Returns:
            OperatorFilter: An instance of the OperatorFilter created from the dictionary.
        """

        if "field" not in base_dict_filter:
            raise MissingParameterSpecification(
                "field", "MaxAbsoluteDifferenceSpecification"
            )
        if "value" not in base_dict_filter:
            raise MissingParameterSpecification(
                "value",
                "MaxAbsoluteDifferenceSpecification",
                name_field=base_dict_filter["field"],
            )
        if "range" not in base_dict_filter:
            raise MissingParameterSpecification(
                "range",
                "MaxAbsoluteDifferenceSpecification",
                name_field=base_dict_filter["field"],
            )
        if "typeField" not in base_dict_filter:
            raise MissingParameterSpecification(
                "typeField",
                "MaxAbsoluteDifferenceSpecification",
                name_field=base_dict_filter["field"],
            )
        if "isActivated" not in base_dict_filter:
            base_dict_filter["isActivated"] = True
        if "defaultState" not in base_dict_filter:
            base_dict_filter["defaultState"] = False

        return MaxAbsoluteDifferenceFilter(
            activated=base_dict_filter["isActivated"],
            default_state=base_dict_filter["defaultState"],
            field_comparison=base_dict_filter["field"],
            type_field=base_dict_filter["typeField"],
            central_value=base_dict_filter["value"],
            range=base_dict_filter["range"],
        )

    def generate_dict(self):
        """Generate a dictionary representation of the OperatorFilter.

        Returns:
            dict: A dictionary representation of the OperatorFilter.
        """
        return {
            "type": "MaxAbsoluteDifferenceSpecification",
            "isActivated": self.activated,
            "defaultState": self.default_state,
            "field": self.field_comparison,
            "typeField": self.type_field,
            "value": self.central_value,
            "range": self.range,
        }


class ArrayFilter(BaseFilter):
    """A filter that represents a comparison operation on a specific field of an event.

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated.
        field (str): The field to be compared.
        value: The value for the comparison.

    Methods:
        apply_filter(event): Apply the ArrayFilter to an event.
        create_from_dict(base_dict_filter): Create an ArrayFilter from a dictionary.
        generate_dict(): Generate a dictionary representation of the ArrayFilter.
    """

    def __init__(self, activated, field, value, default_state=False):
        """Initialize an ArrayFilter with the specified activation status and parameters.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            default_state (bool): The boolean value which is returned when the filter is deactivated.
            field (str): The field to be compared.
            value: The value for the comparison.
        """
        super().__init__(activated, default_state)
        self.field = field
        self.value = value

    def apply_filter(self, event):
        """Apply the ArrayFilter to an event.

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: True if the event passes the ArrayFilter, False otherwise.
        """
        if not self.activated:
            return self.default_state

        if self.field not in event:
            return False

        if type(event[self.field]) is not list:
            return False

        return self.value in event[self.field]

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Create an ArrayFilter from a dictionary representation.

        Args:
            base_dict_filter (dict): A dictionary representation of the ArrayFilter.

        Returns:
            ArrayFilter: An instance of the ArrayFilter created from the dictionary.
        """
        if "field" not in base_dict_filter:
            raise MissingParameterSpecification("field", "ArraySpecification")
        if "value" not in base_dict_filter:
            raise MissingParameterSpecification(
                "value", "ArraySpecification", base_dict_filter["field"]
            )
        if "isActivated" not in base_dict_filter:
            base_dict_filter["isActivated"] = True
        if "defaultState" not in base_dict_filter:
            base_dict_filter["defaultState"] = False

        return ArrayFilter(
            activated=base_dict_filter["isActivated"],
            default_state=base_dict_filter["defaultState"],
            field=base_dict_filter["field"],
            value=base_dict_filter["value"],
        )

    def generate_dict(self):
        """Generate a dictionary representation of the OperatorFilter.

        Returns:
            dict: A dictionary representation of the OperatorFilter.
        """
        return {
            "type": "ArraySpecification",
            "isActivated": self.activated,
            "defaultState": self.default_state,
            "field": self.field,
            "value": self.value,
        }


class ContainsFilter(BaseFilter):
    """A filter that checks if a specified value is contained within a field of an event.

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated.
        field (str): The field to be checked.
        value (str): The value to search for within the field.

    Methods:
        apply_filter(event): Apply the ContainsFilter to an event.
        create_from_dict(base_dict_filter): Create a ContainsFilter from a dictionary.
    """

    def __init__(self, activated: bool, field: str, value: str, default_state=False):
        """Initialize a ContainsFilter with the specified activation status and parameters.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            field (str): The field to be checked.
            value (str): The value to search for within the field.
            default_state (bool, optional): The boolean value which is returned when the filter is deactivated.
        """
        super().__init__(activated, default_state)
        self.field = field
        self.value = value

    def apply_filter(self, event):
        """Apply the ContainsFilter to an event.

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: True if the event passes the ContainsFilter, False otherwise.
        """
        if not self.activated:
            return self.default_state

        if self.field not in event:
            return False

        if type(event[self.field]) is not str:
            return False

        return str(self.value).lower() in str(event[self.field]).lower()

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Create a ContainsFilter from a dictionary representation.

        Args:
            base_dict_filter (dict): A dictionary representation of the ContainsFilter.

        Returns:
            ContainsFilter: An instance of the ContainsFilter created from the dictionary.
        """
        if "field" not in base_dict_filter:
            raise MissingParameterSpecification("field", "ContainsSpecification")
        if "value" not in base_dict_filter:
            raise MissingParameterSpecification(
                "value", "ContainsSpecification", base_dict_filter["field"]
            )
        if "isActivated" not in base_dict_filter:
            base_dict_filter["isActivated"] = True
        if "defaultState" not in base_dict_filter:
            base_dict_filter["defaultState"] = False

        return ContainsFilter(
            activated=base_dict_filter["isActivated"],
            field=base_dict_filter["field"],
            value=base_dict_filter["value"],
            default_state=base_dict_filter["defaultState"],
        )

    def generate_dict(self):
        """Generate a dictionary representation of the OperatorFilter.

        Returns:
            dict: A dictionary representation of the OperatorFilter.
        """
        return {
            "type": "ContainsSpecification",
            "isActivated": self.activated,
            "defaultState": self.default_state,
            "field": self.field,
            "value": self.value,
        }


class ConfidentialObservatoryFilter(BaseFilter):
    """Hides events restricted to observatories the user is not a member of.

    ``confidential_observatory`` is the single marker for restricted data. It
    holds the short names of the observatories allowed to see the event, joined
    by commas when an event accumulates more than one (see
    ``Voevent.update_vo_from_colibri_db``). An empty or missing value means the
    event is public.

    The check is fail-closed: an event passes only when EVERY name it carries is
    one the user is a member of. A tag nobody is a member of (a new observatory,
    a typo in the admin event editor) therefore hides the event rather than
    publishing it, which is the safe direction for a confidentiality gate.

    Comparison is case-insensitive: events are tagged in lower case ("hess")
    while observatory short names are the upper-case document ids ("HESS").

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated.
        authorized_short_names (set): observatory short names the user may see
            restricted data for. Empty means anonymous / no grants.
    """

    FIELD = "confidential_observatory"

    def __init__(self, activated, authorized_short_names=None, default_state=False):
        """Initialize the filter with the user's authorised observatories.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            authorized_short_names (set|None): observatory short names the user
                is a member of. ``None`` is treated as "no grants".
            default_state (bool, optional): The boolean value which is returned when the filter is deactivated.
        """
        super().__init__(activated, default_state)
        self.authorized_short_names = {
            str(name).strip().lower()
            for name in (authorized_short_names or set())
            if str(name).strip()
        }

    def apply_filter(self, event):
        """Apply the ConfidentialObservatoryFilter to an event.

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: True if the user may see the event, False otherwise.
        """
        if not self.activated:
            return self.default_state

        if self.FIELD not in event:
            return True

        raw = event[self.FIELD]
        # A missing value means "public". It reaches us in several shapes: None
        # from a dict, and float("nan") when the events were assembled into a
        # pandas DataFrame (catalog_search builds one and filters row-wise), in
        # which case documents predating the field get NaN rather than "".
        # `raw != raw` is the NaN test. Getting this wrong is expensive in this
        # direction: because the filter is fail-closed, treating NaN as a tag
        # would hide every event that lacks the field.
        if raw is None or raw != raw:
            return True

        tags = [tag.strip().lower() for tag in str(raw).split(",")]
        tags = [tag for tag in tags if tag and tag not in ("nan", "none", "null")]
        if not tags:
            return True

        return all(tag in self.authorized_short_names for tag in tags)

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Not supported: this filter is built server-side from the user's
        memberships and must never be constructible from a client payload."""
        raise UnknownFilterSpecification("ConfidentialObservatorySpecification")

    def generate_dict(self):
        """Generate a dictionary representation of the ConfidentialObservatoryFilter.

        Returns:
            dict: A dictionary representation of the ConfidentialObservatoryFilter.
        """
        return {
            "type": "ConfidentialObservatorySpecification",
            "isActivated": self.activated,
            "defaultState": self.default_state,
            "field": self.FIELD,
            "authorizedShortNames": sorted(self.authorized_short_names),
        }


def extract_numeric_value(input_string: str) -> float | None:
    """Extract the numeric value from a string that may contain a unit.

    Handles three cases:
    1. String with space separator: "10.5 GeV" -> 10.5
    2. String without space: "100km" or "100" -> tries direct parsing
    3. Leading numeric part extraction: "100km" -> 100

    Args:
        input_string (str): The input string potentially containing a number and unit.

    Returns:
        float | None: The extracted numeric value, or None if parsing fails.
    """
    import re

    trimmed = input_string.strip()

    # Case 1: Try splitting by space first
    if " " in trimmed:
        parts = trimmed.split(" ")
        if parts:
            try:
                return float(parts[0])
            except ValueError:
                pass

    # Case 2: Try parsing the whole string directly (no unit or no space)
    try:
        return float(trimmed)
    except ValueError:
        pass

    # Case 3: Try to extract leading numeric part from string like "100km"
    match = re.match(r"^-?\d+\.?\d*", trimmed)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            pass

    return None


class NumericStringFilter(BaseFilter):
    """A filter that compares numeric values extracted from strings that may contain units.

    This filter is useful for filtering events where parameters are stored as strings
    like "10.5 GeV", "100 km", or "50TeV". The unit is discarded and only the numeric
    part is compared against the filter value.

    Attributes:
        activated (bool): A boolean value indicating whether the filter is active.
        default_state (bool): The boolean value which is returned when the filter is deactivated.
        field (str): The field to be compared.
        operator (str): The comparison operator (e.g., '==', '<', '>', '<=', '>=', '!=').
        comparison_value (float): The numeric value to compare against.

    Methods:
        apply_filter(event): Apply the NumericStringFilter to an event.
        create_from_dict(base_dict_filter): Create a NumericStringFilter from a dictionary.
        generate_dict(): Generate a dictionary representation of the NumericStringFilter.
    """

    def __init__(
        self,
        activated: bool,
        field: str,
        operator: str,
        comparison_value: float,
        default_state: bool = False,
    ):
        """Initialize a NumericStringFilter with the specified activation status and parameters.

        Args:
            activated (bool): A boolean value indicating whether the filter is active.
            field (str): The field to be compared.
            operator (str): The comparison operator (e.g., '==', '<', '>', '<=', '>=', '!=').
            comparison_value (float): The numeric value to compare against.
            default_state (bool, optional): The boolean value which is returned when the filter is deactivated.
        """
        super().__init__(activated, default_state)
        self.field = field
        self.operator = operator
        self.comparison_value = float(comparison_value)

        if operator not in ["==", "!=", "<", "<=", ">", ">="]:
            raise UnknownOperatorFieldSpecification(operator)

    def apply_filter(self, event):
        """Apply the NumericStringFilter to an event.

        Extracts the numeric value from the field (discarding any unit),
        then compares it with the filter value using the specified operator.

        Args:
            event (dict): The event to which the filter is applied.

        Returns:
            bool: True if the event passes the NumericStringFilter, False otherwise.
        """
        if not self.activated:
            return self.default_state

        if self.field not in event:
            return False

        field_value = event[self.field]
        if field_value is None:
            return False

        # Extract numeric value from the field (which may contain a unit)
        extracted_value = extract_numeric_value(str(field_value))
        if extracted_value is None:
            return False

        # Compare based on operator
        if self.operator == "==":
            return extracted_value == self.comparison_value
        elif self.operator == "!=":
            return extracted_value != self.comparison_value
        elif self.operator == ">":
            return extracted_value > self.comparison_value
        elif self.operator == ">=":
            return extracted_value >= self.comparison_value
        elif self.operator == "<":
            return extracted_value < self.comparison_value
        elif self.operator == "<=":
            return extracted_value <= self.comparison_value
        else:
            raise UnknownOperatorFieldSpecification(self.operator)

    @staticmethod
    def create_from_dict(base_dict_filter):
        """Create a NumericStringFilter from a dictionary representation.

        Args:
            base_dict_filter (dict): A dictionary representation of the NumericStringFilter.

        Returns:
            NumericStringFilter: An instance of the NumericStringFilter created from the dictionary.
        """
        if "field" not in base_dict_filter:
            raise MissingParameterSpecification("field", "NumericStringSpecification")
        if "value" not in base_dict_filter:
            raise MissingParameterSpecification(
                "value", "NumericStringSpecification", base_dict_filter["field"]
            )
        if "operation" not in base_dict_filter:
            raise MissingParameterSpecification(
                "operation", "NumericStringSpecification", base_dict_filter["field"]
            )
        if "isActivated" not in base_dict_filter:
            base_dict_filter["isActivated"] = True
        if "defaultState" not in base_dict_filter:
            base_dict_filter["defaultState"] = False

        return NumericStringFilter(
            activated=base_dict_filter["isActivated"],
            default_state=base_dict_filter["defaultState"],
            field=base_dict_filter["field"],
            operator=base_dict_filter["operation"],
            comparison_value=base_dict_filter["value"],
        )

    def generate_dict(self):
        """Generate a dictionary representation of the NumericStringFilter.

        Returns:
            dict: A dictionary representation of the NumericStringFilter.
        """
        return {
            "type": "NumericStringSpecification",
            "isActivated": self.activated,
            "defaultState": self.default_state,
            "field": self.field,
            "operation": self.operator,
            "value": self.comparison_value,
        }


class BaseClassExceptionFilterParsing(Exception):
    """Base exception class for error when parsing filter

    Args:
        exception_message (str): The message of the exception
    """

    def __init__(self, exception_message):
        super().__init__(exception_message)

    @abstractmethod
    def generate_error_message_user(self):
        pass


class UnknownFilterSpecification(BaseClassExceptionFilterParsing):
    """Exception for unknown filter specification types.

    Args:
        specification_name (str): The name of the unknown filter specification.
    """

    def __init__(self, specification_name):
        self.specification_name = specification_name
        super().__init__(self.generate_error_message_user())

    def generate_error_message_user(self):
        return "Unknown specification name : " + str(self.specification_name)


class UnknownOperatorFieldSpecification(BaseClassExceptionFilterParsing):
    """Exception for an unknown operator in FieldSpecification.

    This exception is raised when an unknown operator is encountered in a FieldSpecification.

    Args:
        operator_name (str): The name of the unknown operator.
    """

    def __init__(self, operator_name):
        self.operator_name = operator_name
        super().__init__(self.generate_error_message_user())

    def generate_error_message_user(self):
        return (
            "Unknown filter operation : "
            + str(self.operator_name)
            + " in FieldSpecification"
        )


class UnknownTypeValueSpecification(BaseClassExceptionFilterParsing):
    """Exception for an unknown operator in FieldSpecification.

    This exception is raised when an unknown type is encountered in a FieldSpecification.

    Args:
        type_name (str): The name of the unknown operator.
    """

    def __init__(self, type_name, specification_name):
        self.type_name = type_name
        self.specification_name = specification_name
        super().__init__(self.generate_error_message_user())

    def generate_error_message_user(self):
        return (
            "Unknown type for field : "
            + str(self.type_name)
            + " in "
            + self.specification_name
        )


class MissingArrayIndexSpecification(BaseClassExceptionFilterParsing):
    """Exception for missing array index in FieldSpecification.

    This exception is raised when an unknown type is encountered in a FieldSpecification.

    Args:
        type_name (str): The name of the field with the array
    """

    def __init__(self, array_name, specification_name):
        self.array_name = array_name
        self.specification_name = specification_name
        super().__init__(self.generate_error_message_user())

    def generate_error_message_user(self):
        return (
            "Need an array index for for field : "
            + str(self.array_name)
            + " in "
            + self.specification_name
        )


class MissingParameterSpecification(BaseClassExceptionFilterParsing):
    """Exception for missing parameters in a filter specification dictionary.

    This exception is raised when a required parameter is missing from a filter specification dictionary.

    Args:
        parameter_name (str): The name of the missing parameter.
        specification_name (str): The name of the filter specification.
    """

    def __init__(self, parameter_name, specification_name, name_field=None):
        self.parameter_name = parameter_name
        self.specification_name = specification_name
        self.name_field = name_field
        super().__init__(self.generate_error_message_user())

    def generate_error_message_user(self):
        if self.name_field is None:
            return (
                "Missing "
                + str(self.parameter_name)
                + " in dictionary of specification "
                + str(self.specification_name)
            )
        else:
            return (
                "Missing "
                + str(self.parameter_name)
                + " in dictionary of specification "
                + str(self.specification_name)
                + " filtering on the parameter "
                + self.name_field
            )


class EmptyFilterList(BaseClassExceptionFilterParsing):
    """Exception for an empty sub-filter list in AndSpecification or OrSpecification.

    This exception is raised when an AndSpecification or OrSpecification has an empty list of sub-filters.

    Args:
        specification_name (str): The name of the specification with an empty sub-filter list.
    """

    def __init__(self, specification_name):
        self.specification_name = specification_name
        super().__init__(self.generate_error_message_user())

    def generate_error_message_user(self):
        return "The sub-filter list of " + str(self.specification_name) + " is empty"


def create_filter_from_dict(filters_dict: dict) -> dict:
    # create dicts
    obs_filters = {"type": "OrSpecification", "isActivated": True, "specs": []}

    event_type_filters = {"type": "OrSpecification", "isActivated": True, "specs": []}

    general_filters = {
        "type": "OrSpecification",
        "isActivated": True,
        "defaultState": True,
        "specs": [],
    }

    try:
        for filter in filters_dict["obs"]:
            if filter["isActivated"]:
                obs_filters["specs"].append(filter["filter"])
            elif filter["defaultState"]:
                obs_filters["specs"].append({"type": "TrueSpecification"})
            else:
                obs_filters["specs"].append({"type": "FalseSpecification"})

        for filter in filters_dict["type"]:
            if filter["isActivated"]:
                event_type_filters["specs"].append(filter["filter"])
            elif filter["defaultState"]:
                event_type_filters["specs"].append({"type": "TrueSpecification"})
            else:
                event_type_filters["specs"].append({"type": "FalseSpecification"})

        for filter in filters_dict["general"]:
            if filter["isActivated"]:
                general_filters["specs"].append(filter["filter"])
            elif filter["defaultState"]:
                general_filters["specs"].append({"type": "TrueSpecification"})
            else:
                general_filters["specs"].append({"type": "FalseSpecification"})

    except Exception:
        raise Exception("Error while creating filters from dict")

    # create final filter
    final_filter = {
        "type": "AndSpecification",
        "isActivated": True,
        "specs": [obs_filters, event_type_filters, general_filters],
    }

    return final_filter


def _filter_version_key(name):
    """Sort key of a ``filters_v<major>_<minor>_<patch>`` user-document field."""
    try:
        return tuple(int(part) for part in name.removeprefix("filters_v").split("_"))
    except ValueError:
        return (0,)


def latest_saved_filter_configuration(user_doc_dict):
    """The newest filter configuration saved in a user document.

    The app stores one configuration per filter version (``filters_v2_32_0``,
    ...) and only ever adds new ones, so the highest version is the one the
    user currently sees.

    Args:
        user_doc_dict (dict): The user's Firestore document.

    Returns:
        tuple(str, dict) | None: The version key and its configuration (the
        ``obs`` / ``type`` / ``general`` lists ``create_filter_from_dict``
        expects), or None if the user has never saved filters.
    """
    if not isinstance(user_doc_dict, dict):
        return None
    configurations = {
        key: value
        for key, value in user_doc_dict.items()
        if key.startswith("filters_v") and isinstance(value, dict)
    }
    if not configurations:
        return None
    latest = max(configurations, key=_filter_version_key)
    return latest, configurations[latest]


def create_filter_dict_from_bdd_entry(filters_bdd):
    """
    Create a unique json filter description from a BDD entry


    Args:
        filters_bdd (dict): A dictionary representation of the BDD entry.

    Returns:
        final_filter: a dict describing a single filter that regroup all the others
    """

    try:
        # Create a filter containing all observatory filters
        observatory_filters = {
            "type": "OrSpecification",
            "isActivated": True,
            "spec": [],
        }
        if len(filters_bdd["obs"]) < 1:
            return None
        for k in filters_bdd["obs"].keys():
            observatory_filters["spec"].append(filters_bdd["obs"][k]["filter"])
            observatory_filters["spec"][-1]["isActivated"] = filters_bdd["obs"][k][
                "isActivated"
            ]

        # Create a filter containing all event property filters
        events_type_filters = {
            "type": "OrSpecification",
            "isActivated": True,
            "spec": [],
        }
        if len(filters_bdd["type"]) < 1:
            return None
        for k in filters_bdd["type"].keys():
            events_type_filters["spec"].append(filters_bdd["type"][k]["filter"])
            events_type_filters["spec"][-1]["isActivated"] = filters_bdd["type"][k][
                "isActivated"
            ]

        # Creation of final filter combining all filters
        final_filter = {
            "type": "AndSpecification",
            "isActivated": True,
            "spec": [observatory_filters, events_type_filters],
        }
    except Exception:
        logging.error(traceback.format_exc())
        final_filter = None

    return final_filter


def authorized_observatory_short_names(user_doc_dict):
    """Observatory short names the user is authorised for (data visibility).

    Read exclusively from the community-observatory memberships
    (``observatory_access``), which only the server writes (see the
    ``userServerOnlyKeys()`` allowlist in ``firestore.rules``).

    The legacy ``ObsAuth`` map is deliberately NOT consulted: it stays
    client-writable by design, so honouring it here let any signed-in user
    self-grant access to restricted data by writing their own user document.
    """
    names = set()
    if not isinstance(user_doc_dict, dict):
        return names
    access = user_doc_dict.get("observatory_access")
    if isinstance(access, dict):
        for short_name, entry in access.items():
            if isinstance(entry, dict) and entry.get("member") is True:
                names.add(short_name)
    return names


def add_filter_user_authorisation(authorized_short_names, base_filter):
    """
    Restrict a filter system to the observatories the user is authorised for.

    Args:
        authorized_short_names (set|None): observatory short names the user may
            see restricted data for (see ``authorized_observatory_short_names``).
            ``None`` means anonymous / no user -> default-deny (hide all).
        base_filter (BaseFilter): the actual filter system

    Returns:
        final_filter: The resulting filter system
    """

    if authorized_short_names is None:
        authorized_short_names = set()

    # One restriction covers every observatory. It used to be one hardcoded
    # comparison per stream, with H.E.S.S. keyed on the observatory name
    # ("FLaapLUC@HESS") and SVOM on confidential_observatory; those comparisons
    # were also exact, so an event tagged for two observatories ("hess,svom")
    # matched neither and slipped past both restrictions.
    return AndFilter(
        activated=True,
        sub_filters=[
            ConfidentialObservatoryFilter(
                activated=True,
                authorized_short_names=authorized_short_names,
            ),
            base_filter,
        ],
    )
