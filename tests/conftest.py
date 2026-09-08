"""在收集测试、导入应用前隔离数据库、偏好、日志和缓存。"""

from scripts.test_environment import isolated_environment

_environment = isolated_environment()
_test_root = _environment.__enter__()

import matplotlib

matplotlib.use("Agg")


def pytest_unconfigure(config):
    _environment.__exit__(None, None, None)
