"""Exercise the actual recovered IRQ functions with mocked SPI/FIFO boundaries.

This validates decoded protocol state transitions, not electrical timing or
hardware operation. The test TU uses the function bodies from the build tree.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'

HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include "pico_station_protocol.h"
typedef unsigned char u8;
typedef unsigned int irqreturn_t;
#define IRQ_NONE 0
#define IRQ_HANDLED 1
#define IRQ_WAKE_THREAD 2
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,y) ((x)=(y))
#define max_t(type,a,b) ((type)(a)>(type)(b)?(type)(a):(type)(b))
struct mock_spi { int dev; } spi;
struct kfifo { unsigned int length; unsigned char data[131072]; };
struct spidev_data {
 struct mock_spi *spi;
 bool update_mode, read_pending;
 unsigned int users, pending_payload;
 unsigned char *rx_buffer;
 struct kfifo fifo;
 int buf_lock, fifo_lock, fifo_proc_list;
};
static unsigned int bufsiz=4096;
static unsigned int spi_calls, requested, wakes, warnings, errors;
static int spi_result;
static unsigned char reply[65535];
static void mutex_lock(int *lock) { assert(!*lock); *lock=1; }
static void mutex_unlock(int *lock) { assert(*lock); *lock=0; }
static unsigned int kfifo_len(struct kfifo *fifo) { return fifo->length; }
static void kfifo_reset(struct kfifo *fifo) { fifo->length=0; }
static unsigned int kfifo_in_spinlocked(struct kfifo *fifo, unsigned char *src,
 unsigned int length, int *lock) {
 unsigned int available=sizeof(fifo->data)-fifo->length;
 unsigned int count=length<available?length:available;
 memcpy(fifo->data+fifo->length,src,count); fifo->length+=count; return count;
}
static int spidev_sync_read(struct spidev_data *dev,unsigned int length) {
 assert(dev->buf_lock==1); spi_calls++; requested=length;
 assert(length<=sizeof(reply)); memcpy(dev->rx_buffer,reply,length);
 return spi_result==-999?(int)length:spi_result;
}
#define dev_err_ratelimited(...) (errors++)
#define dev_warn_ratelimited(...) (warnings++)
static void wake_up_interruptible(int *wait) { wakes++; }
static struct { int state_lock, count; } mcudev;
static void *reg;
static int regulator_result, enable_calls, disable_calls;
static int regulator_enable(void *unused) { enable_calls++; return regulator_result; }
static int regulator_disable(void *unused) { disable_calls++; return regulator_result; }
#define printk(...) ((void)0)
/* RECOVERED_FUNCTIONS */
static void reset(struct spidev_data *dev) {
 memset(dev,0,sizeof(*dev)); dev->spi=&spi; dev->users=1;
 dev->rx_buffer=malloc(sizeof(reply)); assert(dev->rx_buffer);
 memset(reply,0,sizeof(reply)); spi_result=-999;
 spi_calls=requested=wakes=warnings=errors=0;
}
static void done(struct spidev_data *dev) { assert(dev->buf_lock==0); free(dev->rx_buffer); }
int main(void) {
 struct spidev_data *dev=malloc(sizeof(*dev)); assert(dev);
 reset(dev);
 reply[0]=0xa5; reply[1]=0x10; reply[4]=6;
 assert(spidev_station_hard_irq(0,dev)==IRQ_WAKE_THREAD);
 assert(spidev_station_thread(0,dev)==IRQ_HANDLED);
 assert(requested==40 && dev->fifo.length==40 && dev->pending_payload==6 && wakes==1);
 /* Payload bytes happen to resemble another header; they must not recurse. */
 reply[4]=9;
 spidev_station_thread(0,dev);
 assert(requested==6 && dev->fifo.length==46 && dev->pending_payload==0 && wakes==2);
 done(dev);

 reset(dev); dev->update_mode=true;
 assert(spidev_station_hard_irq(0,dev)==IRQ_NONE);
 spidev_station_thread(0,dev); assert(spi_calls==0 && wakes==0);
 dev->read_pending=true;
 assert(spidev_station_hard_irq(0,dev)==IRQ_WAKE_THREAD);
 spidev_station_thread(0,dev);
 assert(requested==40 && !dev->read_pending && wakes==1);
 done(dev);

 reset(dev); dev->users=0;
 spidev_station_thread(0,dev); assert(spi_calls==0);
 dev->pending_payload=8;
 spidev_station_thread(0,dev); assert(requested==8 && dev->pending_payload==0);
 done(dev);

 reset(dev); spi_result=-5; dev->read_pending=true;
 spidev_station_thread(0,dev);
 assert(dev->fifo.length==0 && dev->read_pending && errors==1 && wakes==0);
 done(dev);

 reset(dev); dev->pending_payload=65535;
 spidev_station_thread(0,dev);
 assert(requested==65535 && dev->fifo.length==65535 && dev->pending_payload==0);
 done(dev);

 reset(dev); dev->fifo.length=PICO_STATION_FIFO_BYTES;
 spidev_station_thread(0,dev); assert(dev->fifo.length==40);
 done(dev);

 reset(dev); dev->fifo.length=sizeof(dev->fifo.data)-10;
 spidev_station_thread(0,dev); assert(dev->fifo.length==sizeof(dev->fifo.data) && warnings==1);
 done(dev);

 reset(dev); dev->spi=NULL;
 spidev_station_thread(0,dev); assert(spi_calls==0 && wakes==0);
 done(dev); free(dev);
 /* The actual reconstructed power functions must not change the reference
  * count if the regulator operation fails. A redundant power-off is a no-op. */
 regulator_result=-5;
 assert(spidev_mcu_power_on()==-EPERM && spidev_mcu_show_count()==0);
 regulator_result=0;
 assert(spidev_mcu_power_on()==0 && spidev_mcu_show_count()==1);
 regulator_result=-5;
 assert(spidev_mcu_power_off()==-EPERM && spidev_mcu_show_count()==1);
 regulator_result=0;
 assert(spidev_mcu_power_off()==0 && spidev_mcu_show_count()==0);
 assert(spidev_mcu_power_off()==0 && disable_calls==2 && mcudev.state_lock==0);
 puts("station IRQ fixtures passed: header/payload, update gate, close, SPI failure, 65535-byte payload, FIFO reset/overflow, removal");
 return 0;
}
'''


def main():
    output = BASE / 'out/phoenix-kernel-recovery/tests'
    output.mkdir(parents=True, exist_ok=True)
    path = SOURCE / 'drivers/spi/spidev.c'
    source = path.read_text()
    bodies = []
    for name in ['spidev_station_hard_irq', 'spidev_station_thread']:
        m = re.search(r'(?m)^static irqreturn_t ' + name + r'\([^)]*\)\n\{', source)
        if not m:
            raise RuntimeError(f'Cannot locate {name}')
        bodies.append(source[m.start():source.index('\n}\n', m.start()) + 3])
    power_source = (SOURCE / 'drivers/spi/spi-geni-qcom.c').read_text()
    for name in ['spidev_mcu_power_on', 'spidev_mcu_power_off', 'spidev_mcu_show_count']:
        m = re.search(r'(?m)^int ' + name + r'\(void\)\n\{', power_source)
        if not m:
            raise RuntimeError(f'Cannot locate {name}')
        bodies.append(power_source[m.start():power_source.index('\n}\n', m.start()) + 3])
    test = output / 'station-irq-fixtures.c'
    test.write_text(HARNESS.replace('/* RECOVERED_FUNCTIONS */', '\n'.join(bodies)))
    executable = output / 'station-irq-fixtures'
    command = ['gcc', '-std=c11', '-Wall', '-Wextra', '-Wno-unused-parameter',
               '-Werror', '-fsanitize=address,undefined', '-g',
               '-I' + str(SOURCE / 'drivers/spi'), str(test), '-o', str(executable)]
    subprocess.run(command, check=True)
    result = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    print(result.stdout)
    (output / 'station-irq-tests.json').write_text(json.dumps({
        'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'power_source_sha256': hashlib.sha256(power_source.encode()).hexdigest(),
        'actual_kernel_functions_exercised': ['spidev_station_hard_irq', 'spidev_station_thread',
                                              'spidev_mcu_power_on', 'spidev_mcu_power_off', 'spidev_mcu_show_count'],
        'compiler': command, 'exit_code': result.returncode, 'stdout': result.stdout,
        'hardware_tested': False, 'concurrency_tested': False,
        'spi_and_fifo_are_mocks': True
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
