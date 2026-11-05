import platform


def enumerate_ports():
    if platform.system() != 'Windows':
        return {'status': 'NOT_WINDOWS', 'ports': []}
    from serial.tools import list_ports
    return {'status': 'ENUMERATED', 'ports': [{'com': p.device, 'description': p.description}
                                             for p in list_ports.comports()]}
