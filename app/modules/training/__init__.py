from flask import Blueprint

bp = Blueprint('training', __name__)

from . import routes  # noqa: F401, E402
from . import models  # noqa: F401, E402
