"""Hooks system for FreeCAD AI."""
from .registry import HookRegistry

_registry = None

def get_hook_registry() -> HookRegistry:
    global _registry
    if _registry is None:
        _registry = HookRegistry()
    return _registry

def fire_hook(event: str, context: dict) -> dict:
    return get_hook_registry().fire(event, context)
