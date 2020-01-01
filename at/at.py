"""
Basic AT command parsing/encoding library compatible with Nordic's nRF91 series.

NOTE:   Commands are NOT expected to end in <CR><LF> or a NULL.
        Concatenated commands are separated by a ';' (and only first command has 'AT' prefix).
        Custom command prefixes (i.e. "AT#<CMD>") are not used.

See https://infocenter.nordicsemi.com/pdf/nrf91_at_commands_v0.7.pdf for more information.

Most AT commands are represented by a single Python dictionary with 'cmd', 'type', and
'params' keys. The 'cmd' value is arbitrary. The 'type' value can be 'SET', 'READ', or 'TEST'.
The 'params' value is a list of Python values of type None, int, str, or (single-nested) lists.

A few commands use a primary command (e.g. to provide authenticatication)
followed by one or more "concatenated" commands that are sent as part of a single string.
These commands are separated by the ';' character.

Example command string:     'AT+CEMODE=0'
Corresponding dictionary:   {'cmd':'+CEMODE', 'type':'SET', 'params':[0]}

Example command string:     'AT%FOO=7,"c2lnbmF0dXJl";+BAR=(1,2,3)'
Corresponding dictionary:   [{'cmd':'%FOO',
                              'type':'SET',
                              'params':[7, "c2lnbmF0dXJl"]},
                             {'cmd':'+BAR',
                              'type':'SET',
                              'params':[[1, 2, 3]]}]

Responses strings are similar to commands use the same 'params' key and foramt. However,
responses have a 'response' key instead of a 'cmd' key, the 'type' key is set to 'RESPONSE',
an 'error' key is set to True or False.

Example response string:    'OK'
Corresponding dictionary:   {'response':'OK', 'type':'RESPONSE', 'error':False, 'params':[]})

Example response string:    '+CMS ERROR: 128'
Corresponding dictionary:   {'response':'+CMS ERROR',
                             'type':'RESPONSE',
                             'error':True,
                             'params':[128]}

The 'test/tests.py' script contains several example strings and their dictionary equivalents.
"""
AT_CMD_KEY = 'cmd'
AT_TYPE_KEY = 'type'
AT_PARAMS_KEY = 'params'
AT_RESPONSE_KEY = 'response'
AT_ERROR_KEY = 'error'

AT_TYPE_VALUE_SET = 'SET'
AT_TYPE_VALUE_READ = 'READ'
AT_TYPE_VALUE_TEST = 'TEST'
AT_TYPE_VALUE_RESPONSE = 'RESPONSE'

AT_PARAM_SEP = ','
AT_RSP_SEP = ':'
AT_PARAM_CONCAT_SEP = ';'

AT_CMD_PREFIX = 'AT'
AT_CMD_SET_IDENT = '='
AT_CMD_READ_IDENT = '?'
AT_CMD_TEST_IDENT = '=?'
AT_CMD_STRING_IDENT = '"'
AT_CMD_ARRAY_START = '('
AT_CMD_ARRAY_END = ')'

AT_RSP_OK = 'OK'
AT_RSP_ERROR = 'ERROR'

AT_STD_PREFX = '+'
AT_PROP_PREFX = '%'


class ATError(Exception):
    """AT exception class, inherits from the built-in Exception class."""

    def __init__(self, error_str=None):
        """Constructs a new object and sets the error."""
        if error_str:
            self.err_str = 'AT error: {}'.format(error_str)
        else:
            self.err_str = 'AT error'
        Exception.__init__(self, self.err_str)


def _parse_param(param_str):
    """Convert the param_str into its corresponding Python type."""
    if not param_str:
        return None
    elif param_str[0] == AT_CMD_STRING_IDENT:
        return param_str.strip('"')
    else:
        return int(param_str)


def _encode_param(param):
    """Convert the param to its corresponding AT string representation."""
    if param is None:
        return ' '
    elif isinstance(param, str):
        return "".join((AT_CMD_STRING_IDENT, param, AT_CMD_STRING_IDENT))
    else:
        return str(param)


def _parse_params(params_str):
    """Parse an entire string of params, including single-nested arrays."""
    result = []
    array = None
    end_of_array = False
    params = params_str.split(AT_PARAM_SEP)
    for param in params:
        param_str = param.strip()
        if param_str.startswith(AT_CMD_ARRAY_START):
            if array is not None:
                raise ATError("Nested array encountered")
            else:
                array = []
                param_str = param_str[1:]
        if param_str.endswith(AT_CMD_ARRAY_END):
            end_of_array = True
            param_str = param_str[:-1]
        if array is not None:
            array.append(_parse_param(param_str))
        else:
            result.append(_parse_param(param_str))
        if end_of_array:
            result.append(array)
            array = None
            end_of_array = False
    return result


def _encode_params(params_seq):
    """Return a string representation of the params sequence."""
    result_strs = []
    for param in params_seq:
        if not isinstance(param, (list, tuple)):
            result_strs.append(_encode_param(param))
        else:
            seq_str = _encode_params(param)
            result_strs.append(AT_CMD_ARRAY_START + seq_str + AT_CMD_ARRAY_END)
    return AT_PARAM_SEP.join(result_strs)


def parse_string(cmd_str):
    """Return a list of dicts specifying the command."""
    temp_cmd_str = cmd_str.strip().upper()
    if temp_cmd_str.startswith(AT_RSP_OK):
        if len(temp_cmd_str) != len(AT_RSP_OK):
            raise ATError('Unexpected trailing data after OK')
        return {AT_RESPONSE_KEY:AT_RSP_OK,
                AT_TYPE_KEY:AT_TYPE_VALUE_RESPONSE,
                AT_ERROR_KEY:False,
                AT_PARAMS_KEY:[]}
    elif temp_cmd_str.startswith(AT_STD_PREFX) or temp_cmd_str.startswith(AT_PROP_PREFX):
        # Response starting with '+<CMD>: <params>' or '+<CMD> ERROR: <params>'
        response, params = cmd_str.split(AT_RSP_SEP)
        params = _parse_params(params)
        if AT_RSP_ERROR in response:
            return {AT_RESPONSE_KEY:response,
                    AT_TYPE_KEY:AT_TYPE_VALUE_RESPONSE,
                    AT_ERROR_KEY:True,
                    AT_PARAMS_KEY:params}
        else:
            return {AT_RESPONSE_KEY:response,
                    AT_TYPE_KEY:AT_TYPE_VALUE_RESPONSE,
                    AT_ERROR_KEY:False,
                    AT_PARAMS_KEY:params}
    elif cmd_str.endswith(AT_CMD_TEST_IDENT):
        return {AT_CMD_KEY:cmd_str.upper().lstrip(AT_CMD_PREFIX).rstrip(AT_CMD_TEST_IDENT),
                AT_TYPE_KEY:AT_TYPE_VALUE_TEST, AT_PARAMS_KEY:[]}
    elif cmd_str.endswith(AT_CMD_READ_IDENT):
        return {AT_CMD_KEY:cmd_str.upper().lstrip(AT_CMD_PREFIX).rstrip(AT_CMD_TEST_IDENT),
                AT_TYPE_KEY:AT_TYPE_VALUE_READ, AT_PARAMS_KEY:[]}
    else:
        result = []
        stmts = cmd_str.split(AT_PARAM_CONCAT_SEP)
        for stmt in stmts:
            cmd, params = stmt.split(AT_CMD_SET_IDENT)
            result.append({AT_CMD_KEY:cmd.lstrip(AT_CMD_PREFIX),
                           AT_TYPE_KEY:AT_TYPE_VALUE_SET, AT_PARAMS_KEY:_parse_params(params)})
        if len(result) == 1:
            return result[0]
        else:
            return result


def encode_command(cmd_dicts, result_strs=None):
    """Take a list of dicts that describe an AT command string and encode it as string."""
    if not result_strs:
        result_strs = [AT_CMD_PREFIX]
    if not isinstance(cmd_dicts, (tuple, list)):
        cmd_dicts = (cmd_dicts,)

    result_strs.append(cmd_dicts[0][AT_CMD_KEY])
    cmd_type = cmd_dicts[0][AT_TYPE_KEY]
    if  cmd_type == AT_TYPE_VALUE_SET:
        result_strs.append(AT_CMD_SET_IDENT)
        result_strs.append(_encode_params(cmd_dicts[0][AT_PARAMS_KEY]))
    elif cmd_type == AT_TYPE_VALUE_READ:
        result_strs.append(AT_CMD_READ_IDENT)
    elif cmd_type == AT_TYPE_VALUE_TEST:
        result_strs.append(AT_CMD_TEST_IDENT)
    else:
        raise ATError('Unknown command type: {}'.format(cmd_type))

    if len(cmd_dicts) == 1:
        return "".join(result_strs)
    else:
        result_strs.append(AT_PARAM_CONCAT_SEP)
        return "".join(encode_command(cmd_dicts[1:], result_strs))
