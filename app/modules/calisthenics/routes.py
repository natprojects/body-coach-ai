from flask import g, jsonify, request
from app.core.auth import require_auth
from app.extensions import db
from . import bp
from .models import CalisthenicsProfile, CalisthenicsAssessment
