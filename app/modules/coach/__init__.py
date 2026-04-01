from flask import Blueprint

bp = Blueprint('coach', __name__)

from . import models, routes  # noqa
