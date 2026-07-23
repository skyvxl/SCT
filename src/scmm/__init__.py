from scmm.qt_environment import configure_qt_environment
from scmm.version import DISPLAY_VERSION, DISTRIBUTION_VERSION

configure_qt_environment()

__all__ = ["DISPLAY_VERSION", "DISTRIBUTION_VERSION"]
