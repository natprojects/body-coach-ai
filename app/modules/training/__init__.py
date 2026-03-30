from flask import Blueprint
bp = Blueprint('training', __name__)
from . import routes  # noqa
