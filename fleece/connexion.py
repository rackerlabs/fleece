# flake8: noqa

from __future__ import absolute_import

from fleece.handlers.connexion import *
import fleece.log

logger = fleece.log.get_logger(__name__)


logger.warning("fleece.connexion has been moved to fleece.handlers.connexion "
               "- please update as this will not work in future versions.")
