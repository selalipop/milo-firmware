def is_raspberry_pi() -> bool:
    try:
        with open('/proc/cpuinfo', 'r') as f:
            # Check for "Raspberry Pi" or common Pi hardware details in cpuinfo
            cpuinfo = f.read().lower()
            return any(marker in cpuinfo for marker in [
                'raspberry pi',
                'bcm2708',
                'bcm2709',
                'bcm2711',
                'bcm2835',
                'bcm2836',
                'bcm2837'
            ])
    except:
        return False