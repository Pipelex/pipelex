from typing import Any

from pipelex.tools.misc.json_utils import deep_update


class TestDeepUpdate:
    def test_simple_key_update(self):
        """Test updating simple key-value pairs."""
        target = {"key_a": 1, "key_b": 2}
        updates = {"key_b": 3}
        deep_update(target, updates=updates)
        assert target == {"key_a": 1, "key_b": 3}

    def test_add_new_key(self):
        """Test adding new keys to target dictionary."""
        target = {"key_a": 1}
        updates = {"key_b": 2, "key_c": 3}
        deep_update(target, updates=updates)
        assert target == {"key_a": 1, "key_b": 2, "key_c": 3}

    def test_nested_dict_update(self):
        """Test deep update of nested dictionaries."""
        target = {"key_a": 1, "key_b": {"key_x": 2, "key_y": 3}}
        updates = {"key_b": {"key_y": 4, "key_z": 5}}
        deep_update(target, updates=updates)
        assert target == {"key_a": 1, "key_b": {"key_x": 2, "key_y": 4, "key_z": 5}}

    def test_list_override(self):
        """Test that lists are overridden, not concatenated."""
        target = {"key_a": [1, 2, 3]}
        updates = {"key_a": [4, 5]}
        deep_update(target, updates=updates)
        assert target == {"key_a": [4, 5]}

    def test_list_override_in_nested_dict(self):
        """Test that lists in nested dictionaries are overridden."""
        target = {"key_a": {"key_b": [1, 2, 3]}}
        updates = {"key_a": {"key_b": [4, 5]}}
        deep_update(target, updates=updates)
        assert target == {"key_a": {"key_b": [4, 5]}}

    def test_deeply_nested_dict_update(self):
        """Test update of deeply nested dictionaries."""
        target = {
            "level_1": {
                "level_2": {
                    "level_3": {
                        "key_a": 1,
                        "key_b": 2,
                    }
                }
            }
        }
        updates = {
            "level_1": {
                "level_2": {
                    "level_3": {
                        "key_b": 3,
                        "key_c": 4,
                    }
                }
            }
        }
        deep_update(target, updates=updates)
        expected = {
            "level_1": {
                "level_2": {
                    "level_3": {
                        "key_a": 1,
                        "key_b": 3,
                        "key_c": 4,
                    }
                }
            }
        }
        assert target == expected

    def test_mixed_types_update(self):
        """Test updating with mixed types (primitives, dicts, lists)."""
        target = {
            "string": "old",
            "number": 1,
            "nested": {"key_a": 1},
            "array": [1, 2],
        }
        updates = {
            "string": "new",
            "number": 2,
            "nested": {"key_b": 2},
            "array": [3, 4, 5],
        }
        deep_update(target, updates=updates)
        expected = {
            "string": "new",
            "number": 2,
            "nested": {"key_a": 1, "key_b": 2},
            "array": [3, 4, 5],
        }
        assert target == expected

    def test_empty_updates(self):
        """Test that empty updates dictionary doesn't change target."""
        target = {"key_a": 1, "key_b": 2}
        updates: dict[str, Any] = {}
        deep_update(target, updates=updates)
        assert target == {"key_a": 1, "key_b": 2}

    def test_empty_target(self):
        """Test updating an empty target dictionary."""
        target: dict[str, Any] = {}
        updates = {"key_a": 1, "key_b": {"key_c": 2}}
        deep_update(target, updates=updates)
        assert target == {"key_a": 1, "key_b": {"key_c": 2}}

    def test_replace_dict_with_primitive(self):
        """Test replacing a dictionary value with a primitive."""
        target = {"key_a": {"key_b": 1}}
        updates = {"key_a": "string"}
        deep_update(target, updates=updates)
        assert target == {"key_a": "string"}

    def test_replace_primitive_with_dict(self):
        """Test replacing a primitive value with a dictionary."""
        target = {"key_a": "string"}
        updates = {"key_a": {"key_b": 1}}
        deep_update(target, updates=updates)
        assert target == {"key_a": {"key_b": 1}}

    def test_replace_list_with_primitive(self):
        """Test replacing a list with a primitive value."""
        target = {"key_a": [1, 2, 3]}
        updates = {"key_a": "string"}
        deep_update(target, updates=updates)
        assert target == {"key_a": "string"}

    def test_replace_primitive_with_list(self):
        """Test replacing a primitive value with a list."""
        target = {"key_a": "string"}
        updates = {"key_a": [1, 2, 3]}
        deep_update(target, updates=updates)
        assert target == {"key_a": [1, 2, 3]}

    def test_none_values(self):
        """Test handling of None values."""
        target = {"key_a": 1, "key_b": None}
        updates = {"key_a": None, "key_b": 2}
        deep_update(target, updates=updates)
        assert target == {"key_a": None, "key_b": 2}

    def test_empty_list_override(self):
        """Test that empty lists override non-empty lists."""
        target = {"key_a": [1, 2, 3]}
        updates: dict[str, Any] = {"key_a": []}
        deep_update(target, updates=updates)
        assert target == {"key_a": []}

    def test_empty_dict_merge(self):
        """Test merging with empty nested dictionaries."""
        target = {"key_a": {"key_b": 1}}
        updates: dict[str, Any] = {"key_a": {}}
        deep_update(target, updates=updates)
        # Empty dict should merge but not change existing keys
        assert target == {"key_a": {"key_b": 1}}

    def test_complex_nested_structure(self):
        """Test a complex nested structure with multiple levels and types."""
        target = {
            "config": {
                "database": {
                    "host": "localhost",
                    "port": 5432,
                    "credentials": {
                        "username": "admin",
                    },
                },
                "features": ["feature_a", "feature_b"],
            },
            "version": "1.0.0",
        }
        updates = {
            "config": {
                "database": {
                    "port": 3306,
                    "credentials": {
                        "password": "secret",
                    },
                },
                "features": ["feature_c"],
                "cache": {"enabled": True},
            },
            "version": "1.1.0",
        }
        deep_update(target, updates=updates)
        expected = {
            "config": {
                "database": {
                    "host": "localhost",
                    "port": 3306,
                    "credentials": {
                        "username": "admin",
                        "password": "secret",
                    },
                },
                "features": ["feature_c"],
                "cache": {"enabled": True},
            },
            "version": "1.1.0",
        }
        assert target == expected

    def test_boolean_values(self):
        """Test handling of boolean values."""
        target = {"flag_a": True, "flag_b": False}
        updates = {"flag_a": False, "flag_b": True}
        deep_update(target, updates=updates)
        assert target == {"flag_a": False, "flag_b": True}

    def test_numeric_types(self):
        """Test handling of different numeric types."""
        target = {"int_val": 1, "float_val": 1.5}
        updates = {"int_val": 2.5, "float_val": 3}
        deep_update(target, updates=updates)
        assert target == {"int_val": 2.5, "float_val": 3}

    def test_list_of_dicts(self):
        """Test that lists of dictionaries are overridden, not merged."""
        target = {"items": [{"id": 1, "name": "item1"}, {"id": 2, "name": "item2"}]}
        updates = {"items": [{"id": 3, "name": "item3"}]}
        deep_update(target, updates=updates)
        assert target == {"items": [{"id": 3, "name": "item3"}]}

    def test_multiple_level_additions(self):
        """Test adding keys at multiple levels simultaneously."""
        target = {"level_1": {"level_2": {"existing": "value"}}}
        updates = {
            "level_1": {
                "level_2": {"new_key": "new_value"},
                "new_level": {"key": "value"},
            },
            "new_top": "value",
        }
        deep_update(target, updates=updates)
        expected = {
            "level_1": {
                "level_2": {"existing": "value", "new_key": "new_value"},
                "new_level": {"key": "value"},
            },
            "new_top": "value",
        }
        assert target == expected
