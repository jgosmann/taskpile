import signal

signalnames = {}

for key in dir(signal):
    if key.startswith('SIG'):
        signalnames[getattr(signal, key)] = key
