# Fleece

To start using fleece with a lambda project you will need to make 2 small
updates to your project.

* Where you would normally import `logging.get_logger` or `logging.getLogger`
use`fleece.log.get_logger` or `fleece.log.getLogger`


* In the file with your primary lambda handler include
`fleece.log.setup_root_logger()`prior to setting up any additional logging.

This should ensure that all handlers on the root logger are cleaned up and one
with appropriate stream handlers is in place.