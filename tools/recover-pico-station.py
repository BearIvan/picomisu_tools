"""Apply evidence-backed station recovery to the isolated WSL kernel clone."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
TEMPLATES = PROJECT / 'kernel-recovery'


def replace_function(text, name, replacement):
    match = re.search(r'(?m)^(?:static\s+)?(?:inline\s+)?(?:int|ssize_t|unsigned int|__poll_t)\s+'
                      + re.escape(name) + r'\([^)]*\)\s*\n\{', text)
    if not match:
        raise RuntimeError(f'Cannot locate {name}')
    start = match.start()
    # Kernel style has a column-zero closing brace only at function end.
    end = text.index('\n}\n', match.start()) + 3
    return text[:start] + replacement.rstrip() + '\n' + text[end:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh-generated', action='store_true')
    args = parser.parse_args()
    state_path = BASE / 'out/phoenix-kernel-recovery/station-generation-state.json'
    if args.refresh_generated and state_path.exists():
        for relative, expected in json.loads(state_path.read_text()).items():
            path = SOURCE / relative
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f'Managed file changed after generation: {relative}; preserve the edits')
    head = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    branch = subprocess.check_output(['git', '-C', str(SOURCE), 'branch', '--show-current'], text=True).strip()
    if head != 'ceafd3afc0208c03e0eb7a1a60939d147f92d72a' or branch != 'codex/pico-kernel-recovery':
        raise RuntimeError('Unexpected recovery checkout')
    if subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain'], text=True).strip() and not args.refresh_generated:
        raise RuntimeError('Recovery checkout already has changes; preserve them')
    def baseline(relative):
        return subprocess.check_output(['git', '-C', str(SOURCE), 'show', 'HEAD:' + relative], text=True)
    shutil.copy2(TEMPLATES / 'drivers/misc/pico_station.c', SOURCE / 'drivers/misc/pico_station.c')
    shutil.copy2(TEMPLATES / 'drivers/spi/pico_station_protocol.h', SOURCE / 'drivers/spi/pico_station_protocol.h')
    makefile = SOURCE / 'drivers/misc/Makefile'
    makefile.write_text(baseline('drivers/misc/Makefile') + '\nobj-$(CONFIG_CONTROLLER_STATION) += pico_station.o\n')
    kconfig = SOURCE / 'drivers/misc/Kconfig'
    kconfig.write_text(baseline('drivers/misc/Kconfig') + '''
config CONTROLLER_STATION
	bool "PICO controller station IRQ notifications"
	depends on OF && GPIOLIB && SPI_SPIDEV
	help
	  Restore the stationdev notification endpoint used by PICO VR services.
''')
    path = SOURCE / 'drivers/spi/spidev.c'
    text = baseline('drivers/spi/spidev.c')
    text = text.replace('#include <linux/poll.h>', '#include <linux/poll.h>\n#include <linux/kfifo.h>\n#include "pico_station_protocol.h"')
    start = text.index('#define MAX_MISS_DTRY')
    end = text.index('DECLARE_COMPLETION(spi_completion);', start) + len('DECLARE_COMPLETION(spi_completion);')
    text = text[:start] + text[end:]
    start = text.index('struct spidev_data {')
    end = text.index('\n};', start) + 3
    text = text[:start] + '''struct spidev_data {
	dev_t devt;
	spinlock_t spi_lock;
	struct spi_device *spi;
	struct list_head device_entry;
	struct kfifo fifo;
	spinlock_t fifo_lock;
	wait_queue_head_t fifo_proc_list;
	struct mutex buf_lock;
	unsigned int users;
	u8 *tx_buffer;
	u8 *rx_buffer;
	u32 speed_hz;
	int boot_gpio;
	int station_irq_gpio;
	bool read_pending;
	bool update_mode;
	u16 pending_payload;
	int station_irq;
	bool irq_requested;
};''' + text[end:]
    text = text.replace('\nspidev_sync_read_write(', '\nssize_t\nspidev_sync_read_write(')
    start = text.index('static irqreturn_t ultrasonic_interrupt(')
    end = text.index('\n}\n', start) + 3
    text = text[:start] + text[end:]
    helpers = '''
static void spidev_station_free(struct spidev_data *spidev)
{
	kfifo_free(&spidev->fifo);
	kfree(spidev->tx_buffer);
	kfree(spidev->rx_buffer);
	kfree(spidev);
}

static irqreturn_t spidev_station_hard_irq(int irq, void *data)
{
	struct spidev_data *spidev = data;
	if (READ_ONCE(spidev->update_mode) && !READ_ONCE(spidev->read_pending))
		return IRQ_NONE;
	return IRQ_WAKE_THREAD;
}

static irqreturn_t spidev_station_thread(int irq, void *data)
{
	struct spidev_data *spidev = data;
	unsigned int length, inserted;
	bool payload;
	int result;
	mutex_lock(&spidev->buf_lock);
	if (!spidev->spi || (spidev->update_mode && !spidev->read_pending) ||
		(!READ_ONCE(spidev->users) && !spidev->pending_payload))
		goto out;
	if (kfifo_len(&spidev->fifo) == PICO_STATION_FIFO_BYTES)
		kfifo_reset(&spidev->fifo);
	payload = spidev->pending_payload != 0;
	length = payload ? spidev->pending_payload : PICO_STATION_HEADER_BYTES;
	if (length > max_t(unsigned int, bufsiz, 65535)) {
		dev_err_ratelimited(&spidev->spi->dev, "station payload exceeds SPI buffer: %u\\n", length);
		spidev->pending_payload = 0;
		goto out;
	}
	result = spidev_sync_read(spidev, length);
	if (result < 0 || (unsigned int)result != length) {
		dev_err_ratelimited(&spidev->spi->dev, "station SPI read failed: %d\\n", result);
		goto out;
	}
	inserted = kfifo_in_spinlocked(&spidev->fifo, spidev->rx_buffer,
		length, &spidev->fifo_lock);
	if (inserted != length)
		dev_warn_ratelimited(&spidev->spi->dev, "station FIFO overflow\\n");
	spidev->pending_payload = payload ? 0 : pico_station_next_payload(spidev->rx_buffer);
	WRITE_ONCE(spidev->read_pending, false);
	wake_up_interruptible(&spidev->fifo_proc_list);
out:
	mutex_unlock(&spidev->buf_lock);
	return IRQ_HANDLED;
}
'''
    insert = text.index('/* Read-only message with current device setup */')
    text = text[:insert] + helpers + '\n' + text[insert:]
    fragments = (TEMPLATES / 'drivers/spi/spidev_station_functions.c').read_text()
    parts = re.split(r'/\* RECOVER: (\w+) \*/\n', fragments)
    for i in range(1, len(parts), 2):
        text = replace_function(text, parts[i], parts[i + 1])
    text = text.replace('.poll =         spi_poll,', '.poll =         spidev_poll,')
    text = re.sub(r'(\.poll\s*=\s*)spi_poll', r'\1spidev_poll', text)
    # Drop the legacy completion/RFIC-IO2 cases: factory 0x80046b06/07 -> ENOTTY.
    start = text.index('\tcase SPI_IOC_RD_SPI_STATUS:')
    end = text.index('\tcase SPI_IOC_RD_MODE:', start)
    text = text[:start] + text[end:]
    start = text.index('\tcase SPI_IOC_SET_RFIC_IO2_STATUS:')
    end = text.index('\tdefault:', start)
    text = text[:start] + '''	case SPI_IOC_SET_RFIC_IO3_STATUS:
		retval = get_user(tmp, (__u32 __user *)arg);
		if (retval)
			break;
		gpio_set_value(spidev->boot_gpio, !!tmp);
		if (tmp)
			kfifo_reset(&spidev->fifo);
		break;
	case SPI_IOC_SET_POWER_STATUS:
		retval = get_user(tmp, (__u32 __user *)arg);
		if (retval)
			break;
		retval = tmp ? spidev_mcu_power_on() : spidev_mcu_power_off();
		kfifo_reset(&spidev->fifo);
		spidev->pending_payload = 0;
		break;
	case SPI_IOC_GET_POWER_COUNTER:
		retval = put_user(spidev_mcu_show_count(), (__u32 __user *)arg);
		break;
	case SPI_IOC_CLEAN_FIFO:
		kfifo_reset(&spidev->fifo);
		break;
	case SPI_IOC_SET_UPDATE_MODE:
		retval = get_user(tmp, (__u32 __user *)arg);
		if (!retval)
			WRITE_ONCE(spidev->update_mode, !!tmp);
		break;

''' + text[end:]
    # Remove the old post-ioctl handshake, if present.
    text = re.sub(r'\n\s*reinit_completion\(&spi_completion\);', '', text)
    text = re.sub(r'\n\s*atomic_set\(&(?:controller_state|dtry_miss), 0\);', '', text)
    pm = '''
static int spidev_suspend(struct device *dev)
{
	struct spidev_data *spidev = dev_get_drvdata(dev);
	mutex_lock(&device_list_lock);
	if (spidev->irq_requested)
		disable_irq(spidev->station_irq);
	mutex_unlock(&device_list_lock);
	return 0;
}
static int spidev_resume(struct device *dev)
{
	struct spidev_data *spidev = dev_get_drvdata(dev);
	mutex_lock(&device_list_lock);
	if (spidev->irq_requested)
		enable_irq(spidev->station_irq);
	mutex_unlock(&device_list_lock);
	return 0;
}
static SIMPLE_DEV_PM_OPS(spidev_pm_ops, spidev_suspend, spidev_resume);
'''
    text = text.replace('static struct spi_driver spidev_spi_driver = {', pm + '\nstatic struct spi_driver spidev_spi_driver = {')
    text = text.replace('.name =\t\t"spidev",', '.name =\t\t"spidev",\n\t\t.pm = &spidev_pm_ops,')
    text = re.sub(r'^\s*int\s+spi_read_mode = 0;\n', '', text, flags=re.M)
    text = re.sub(r'^\s*int\s+result = 0;\n', '', text, flags=re.M)
    path.write_text(text)
    header = SOURCE / 'include/uapi/linux/spi/spidev.h'
    text = baseline('include/uapi/linux/spi/spidev.h').replace('extern int spidev_mcu_power_on(void);', '''#define SPI_IOC_CLEAN_FIFO _IOR(SPI_IOC_MAGIC, 11, __u32)
#define SPI_IOC_SET_UPDATE_MODE _IOR(SPI_IOC_MAGIC, 12, __u32)
extern int spidev_mcu_show_count(void);
extern int spidev_mcu_power_on(void);''')
    header.write_text(text)
    # Match the factory's successful-only regulator reference count updates.
    path = SOURCE / 'drivers/spi/spi-geni-qcom.c'
    text = baseline('drivers/spi/spi-geni-qcom.c')
    text = text.replace('mcudev.count--;', 'if (!ret)\n\t\t\tmcudev.count--;')
    text = text.replace('mcudev.count++;', 'if (!ret)\n\t\tmcudev.count++;')
    text = text.replace('int spidev_mcu_show_counter(void)', 'int spidev_mcu_show_count(void)')
    text = text.replace('EXPORT_SYMBOL_GPL(spidev_mcu_show_counter);', '''EXPORT_SYMBOL_GPL(spidev_mcu_show_count);
int spidev_mcu_show_counter(void)
{
	return spidev_mcu_show_count();
}
EXPORT_SYMBOL_GPL(spidev_mcu_show_counter);''')
    path.write_text(text)
    managed = ['drivers/misc/pico_station.c', 'drivers/spi/pico_station_protocol.h',
               'drivers/misc/Makefile', 'drivers/misc/Kconfig', 'drivers/spi/spidev.c',
               'drivers/spi/spi-geni-qcom.c', 'include/uapi/linux/spi/spidev.h']
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({relative: hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest()
                                     for relative in managed}, indent=2) + '\n')
    print('Station recovery applied to', SOURCE)


if __name__ == '__main__':
    main()
