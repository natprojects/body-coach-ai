from flask import Blueprint

bp = Blueprint('coach', __name__)

from . import routes  # noqa
