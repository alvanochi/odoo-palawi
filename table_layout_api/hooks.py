import secrets

API_KEY_PARAM = 'foom_table_layout_api.key'


def post_init_hook(env):
    """Creates the API key System Parameter at install time, if it doesn't
    already exist.

    Deliberately NOT done via data/ir_config_parameter.xml:
    ir.config_parameter.key is unique, so XML data for a key that already
    exists (e.g. re-installing over a restored backup) would raise
    IntegrityError. Idempotent here instead -- an existing value is never
    overwritten. Mirrors foom_coa_api's hook.
    """
    icp = env['ir.config_parameter'].sudo()
    if not icp.get_param(API_KEY_PARAM):
        icp.set_param(API_KEY_PARAM, secrets.token_hex(32))
