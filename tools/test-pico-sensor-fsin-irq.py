"""Actual shared FSIN functions with concurrent controllers and GPIO/IRQ models."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/cam_sensor/'
NAMES=[D+n for n in ['pico_sensor_fsin_irq.inc','cam_sensor_core.c','cam_sensor_dev.h']]
MOCKS=r'''
typedef unsigned char u8;
#define IRQF_TRIGGER_RISING 1
struct cam_sensor_ctrl_t {void *sensordata;bool normal,pico_fsin_irq_owned;};
static int Fsin_irq_register,Fsin_gpio_irq,Fsin_gpio=1126;
static int gpio_owned=-1,irq_owned=-1,fail_stage,irq_number=41;
static unsigned requests,directions,mappings,irq_requests,gpio_frees,irq_frees;static void *irq_cookie;
static int cam_sensor_is_normal_camera(struct cam_sensor_ctrl_t *s){return s->normal;}
static int sixdof_4cam_Fsin_irq(int irq,void *data){return 0;}
static int gpio_request(int gpio,const char *name){assert(held==1 && gpio_owned==-1);requests++;if(fail_stage==1)return -EBUSY;gpio_owned=gpio;return 0;}
static int gpio_direction_input(int gpio){assert(held==1 && gpio_owned==gpio);directions++;return fail_stage==2?-EIO:0;}
static int gpio_to_irq(int gpio){assert(held==1 && gpio_owned==gpio);mappings++;return fail_stage==3?-ENXIO:irq_number;}
static int request_irq(int irq,int (*handler)(int,void *),unsigned flags,const char *name,void *cookie){assert(held==1 && irq_owned==-1 && handler==sixdof_4cam_Fsin_irq && flags==1);irq_requests++;if(fail_stage==4)return -EAGAIN;irq_owned=irq;irq_cookie=cookie;return 0;}
static void free_irq(int irq,void *cookie){assert(held==1 && irq_owned==irq && irq_cookie==cookie);irq_frees++;irq_owned=-1;irq_cookie=NULL;}
static void gpio_free(int gpio){assert(held==1 && gpio_owned==gpio);gpio_frees++;gpio_owned=-1;}
static void reset(void){assert(!Fsin_irq_register && gpio_owned==-1 && irq_owned==-1);requests=directions=mappings=irq_requests=gpio_frees=irq_frees=0;fail_stage=0;Fsin_gpio=1126;irq_number=41;}
'''
MAIN=r'''
static pthread_barrier_t ready,release;
static void *worker(void *ptr){struct cam_sensor_ctrl_t *s=ptr;assert(!cam_sensor_register_irq(s));assert(cam_sensor_register_irq(s)==-EALREADY);pthread_barrier_wait(&ready);pthread_barrier_wait(&release);assert(!cam_sensor_unregister_irq(s));assert(!cam_sensor_unregister_irq(s));return NULL;}
int main(void){
 struct cam_sensor_ctrl_t a={.sensordata=(void *)1},b={.sensordata=(void *)1},normal={.sensordata=(void *)1,.normal=true},empty={0};assert(cam_sensor_register_irq(NULL)==-EINVAL);assert(cam_sensor_register_irq(&empty)==-EINVAL);assert(cam_sensor_unregister_irq(NULL)==-EINVAL);assert(!cam_sensor_register_irq(&normal) && !normal.pico_fsin_irq_owned);assert(!cam_sensor_unregister_irq(&normal));
 for(int stage=1;stage<=4;stage++){reset();fail_stage=stage;const int errors[4]={-EBUSY,-EIO,-ENXIO,-EAGAIN};assert(cam_sensor_register_irq(&a)==errors[stage-1] && !a.pico_fsin_irq_owned && !Fsin_irq_register && gpio_owned==-1 && irq_owned==-1 && !irq_frees);assert(gpio_frees==(stage>1));assert(!cam_sensor_unregister_irq(&a) && !Fsin_irq_register);}
 reset();irq_number=0;assert(!cam_sensor_register_irq(&a) && Fsin_irq_register==1 && a.pico_fsin_irq_owned && irq_owned==0);void *cookie=irq_cookie;Fsin_gpio=1127;assert(!cam_sensor_register_irq(&b) && Fsin_irq_register==2 && irq_cookie==cookie && requests==1);assert(!cam_sensor_unregister_irq(&a) && Fsin_irq_register==1 && !a.pico_fsin_irq_owned && !irq_frees);assert(!cam_sensor_unregister_irq(&b) && !Fsin_irq_register && !b.pico_fsin_irq_owned && irq_frees==1 && gpio_frees==1 && gpio_owned==-1 && irq_owned==-1);assert(!cam_sensor_unregister_irq(&b) && !Fsin_irq_register);
 reset();struct cam_sensor_ctrl_t sensors[4];pthread_t threads[4];assert(!pthread_barrier_init(&ready,NULL,5));assert(!pthread_barrier_init(&release,NULL,5));for(unsigned i=0;i<4;i++){sensors[i]=(struct cam_sensor_ctrl_t){.sensordata=(void *)1};assert(!pthread_create(&threads[i],NULL,worker,&sensors[i]));}pthread_barrier_wait(&ready);assert(Fsin_irq_register==4 && requests==1 && irq_requests==1 && !irq_frees);pthread_barrier_wait(&release);for(unsigned i=0;i<4;i++){assert(!pthread_join(threads[i],NULL));assert(!sensors[i].pico_fsin_irq_owned);}assert(!Fsin_irq_register && irq_frees==1 && gpio_frees==1 && !held);pthread_barrier_destroy(&ready);pthread_barrier_destroy(&release);
 puts("PASS: actual shared FSIN register/unregister, all GPIO/IRQ failure unwinds, per-controller ownership/duplicate/idempotent release, IRQ zero, stable cookie/original GPIO, four concurrent controllers create/free shared IRQ once without counter loss/underflow");
}
'''
def main():
    spec=importlib.util.spec_from_file_location('registry',Path(__file__).with_name('test-pico-camera-hub-registry.py'));common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
    code=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+MOCKS+(SOURCE/NAMES[0]).read_text()+MAIN
    out=BASE/'out/phoenix-kernel-recovery/sensor-fsin-irq-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual shared FSIN functions with pthread mutex/barriers and modeled GPIO/IRQ APIs; per-controller ownership and concurrent lifetime verified in host model, no hardware/hot-remove proof','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
