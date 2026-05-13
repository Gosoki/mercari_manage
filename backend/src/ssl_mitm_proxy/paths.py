# -*- coding: utf-8 -*-
import os

from src.app_paths import backend_root_str


def backend_root() -> str:
    return backend_root_str()


def ssl_mitm_data_dir() -> str:
    return os.path.join(backend_root(), "ssl_mitm")
