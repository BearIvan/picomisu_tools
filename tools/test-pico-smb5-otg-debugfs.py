"""Execute the actual qpnp-smb5 OTG debugfs handlers, disable_chg and smb5_create_debugfs bodies under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,re,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
SMB='drivers/power/supply/qcom/qpnp-smb5.c';REG='drivers/power/supply/qcom/smb5-reg.h'
FUNCS=[(SMB,'static int force_batt_psy_update_write('),(SMB,'static int force_usb_psy_update_write('),(SMB,'static int force_dc_psy_update_write('),
       (SMB,'static int disable_chg_write('),(SMB,'static int disable_chg_read('),
       (SMB,'static int otg_current_limit_read('),(SMB,'static int otg_current_limit_write('),
       (SMB,'static int otg_disable_read('),(SMB,'static int otg_disable_write('),(SMB,'static void smb5_create_debugfs(')]
MODEL=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;
#define BIT(n) (1UL<<(n))
#define EINVAL 22
#define EIO 5
#define KERN_ERR ""
static int logs;
#define printk(...) (logs++)
#define pr_err(...) (logs++)
#define dev_err(...) (logs++)
#define IS_ERR_OR_NULL(p) (!(p)||(unsigned long)(p)>=(unsigned long)-4095)
#define S_IFREG 0100000
#define S_IWUSR 0200
#define S_IRUGO 0444
#define S_IWUGO 0222
#define USER_VOTER "USER_VOTER"
#define USER_DAEMON_VOTER "USER_DAEMON_VOTER"
struct device {int id;};struct power_supply {int changed;};struct votable {const char *name;};
struct smb_chg_param {const char *name;u16 reg;int min_u,max_u,step_u;};
struct smb_params {struct smb_chg_param fcc,fv,otg_cl;};
struct smb_charger {struct device *dev;struct smb_params param;struct power_supply *batt_psy,*usb_psy,*dc_psy;
  struct votable *fcc_votable,*chg_disable_votable;int otg_cl_ua;};
struct dentry {char name[32];unsigned mode;void *data;const void *fops;struct dentry *parent;};
struct smb5 {struct smb_charger chg;struct dentry *dfs_root;};
struct debugfs_ops {int (*get)(void *,u64 *);int (*set)(void *,u64);const char *fmt;};
#define DEFINE_DEBUGFS_ATTRIBUTE(n,g,s,f) static const struct debugfs_ops n={g,s,f}
static u32 __debug_mask;
static void power_supply_changed(struct power_supply *p){p->changed++;}
/* PMIC model */
static u8 regs[0x10000];static int read_rc,write_rc,param_rc,writes,param_calls;static int last_param_val;static const struct smb_chg_param *last_param;
static int smblib_read(struct smb_charger *c,u16 a,u8 *v){(void)c;if(read_rc)return read_rc;*v=regs[a];return 0;}
static int smblib_masked_write(struct smb_charger *c,u16 a,u8 m,u8 v){(void)c;writes++;if(write_rc)return write_rc;regs[a]=(regs[a]&~m)|(v&m);return 0;}
static int smblib_set_charge_param(struct smb_charger *c,struct smb_chg_param *p,int v){(void)c;param_calls++;last_param=p;last_param_val=v;
  if(param_rc)return param_rc;regs[p->reg]=(u8)((v-p->min_u)/p->step_u);return 0;}
struct vote_rec {struct votable *v;const char *client;int en,val;};static struct vote_rec votes[16];static int nvotes,vote_rc;
static int vote(struct votable *v,const char *client,int en,int val){assert(nvotes<16);votes[nvotes++]=(struct vote_rec){v,client,en,val};return v->name[0]=='c'?vote_rc:0;}
/* debugfs model */
static struct dentry dents[16];static int ndents,fail_create;
static struct dentry *mk(const char *n,unsigned mode,struct dentry *parent,void *data,const void *fops){assert(ndents<16);
  struct dentry *d=&dents[ndents++];snprintf(d->name,sizeof(d->name),"%s",n);d->mode=mode;d->data=data;d->fops=fops;d->parent=parent;return d;}
static struct dentry *debugfs_create_dir(const char *n,struct dentry *p){return mk(n,040755,p,NULL,NULL);}
static struct dentry *debugfs_create_file(const char *n,unsigned mode,struct dentry *p,void *data,const void *fops){
  if(fail_create&&!strcmp(n,"otg_disable"))return NULL;return mk(n,mode,p,data,fops);}
static struct dentry *debugfs_create_u32(const char *n,unsigned mode,struct dentry *p,u32 *v){return mk(n,mode,p,v,NULL);}
'''
MAIN=r'''
static struct dentry *find(const char *n){for(int i=0;i<ndents;i++)if(!strcmp(dents[i].name,n))return &dents[i];return NULL;}
int main(void){
 struct device dev;struct power_supply bp={0},up={0},dp={0};struct votable fcc={"fcc"},dis={"chg_disable"};
 struct smb5 chip;memset(&chip,0,sizeof(chip));struct smb_charger *chg=&chip.chg;
 chg->dev=&dev;chg->batt_psy=&bp;chg->usb_psy=&up;chg->dc_psy=&dp;chg->fcc_votable=&fcc;chg->chg_disable_votable=&dis;
 chg->param.otg_cl=(struct smb_chg_param){"otg current limit",EXP_OTG_CL_REG,500000,3000000,500000};chg->otg_cl_ua=EXP_DEFAULT_CL;
 u64 v;
 assert(DCDC_CMD_OTG_REG==EXP_CMD_OTG&&OTG_EN_BIT==1);
 /* --- otg_current_limit --- */
 assert(!otg_current_limit_read(chg,&v)&&v==EXP_DEFAULT_CL);
 u64 bad[]={0,1,499999,500001,750000,999999,1000001,1499999,1500001,2000000,3000000,(u64)-1,(u64)1500000+(1ULL<<32)};
 for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++){assert(otg_current_limit_write(chg,bad[i])==-EINVAL);}
 assert(param_calls==0&&chg->otg_cl_ua==EXP_DEFAULT_CL);
 u64 good[]={500000,1000000,1500000};
 for(unsigned i=0;i<4;i++){u64 g=good[i%3];int before=param_calls,prev=chg->otg_cl_ua;assert(!otg_current_limit_write(chg,g));
   assert(chg->otg_cl_ua==(int)g);assert(!otg_current_limit_read(chg,&v)&&v==g);
   if((int)g==prev)assert(param_calls==before); /* unchanged value: no PMIC write */
   else assert(param_calls==before+1&&last_param==&chg->param.otg_cl&&last_param_val==(int)g&&regs[EXP_OTG_CL_REG]==(g-500000)/500000);}
 /* loop ended on 500000: go to 1500000, then repeat it */
 assert(!otg_current_limit_write(chg,1500000));
 int pc=param_calls;assert(!otg_current_limit_write(chg,1500000)&&param_calls==pc);
 /* PMIC failure: error returned, readback keeps the applied value */
 param_rc=-EIO;assert(otg_current_limit_write(chg,500000)==-EIO&&chg->otg_cl_ua==1500000);param_rc=0;
 assert(!otg_current_limit_read(chg,&v)&&v==1500000);
 /* --- otg_disable --- */
 regs[EXP_CMD_OTG]=0xff;assert(!otg_disable_read(chg,&v)&&v==1);regs[EXP_CMD_OTG]=0xfe;assert(!otg_disable_read(chg,&v)&&v==0);
 regs[EXP_CMD_OTG]=0x81;assert(!otg_disable_read(chg,&v)&&v==1);
 read_rc=-EIO;v=77;assert(otg_disable_read(chg,&v)==-EIO&&v==77);read_rc=0;
 writes=0;assert(otg_disable_write(chg,1)==-EINVAL&&otg_disable_write(chg,2)==-EINVAL&&otg_disable_write(chg,(u64)1<<32)==-EINVAL&&!writes);
 regs[EXP_CMD_OTG]=0x81;assert(!otg_disable_write(chg,0)&&writes==1&&regs[EXP_CMD_OTG]==0x80);
 write_rc=-EIO;assert(otg_disable_write(chg,0)==-EIO);write_rc=0;
 /* --- disable_chg (factory 1100 mA step) --- */
 nvotes=0;assert(!disable_chg_write(chg,3));assert(nvotes==2&&votes[0].v==&dis&&!votes[0].en&&votes[1].v==&fcc&&votes[1].en&&votes[1].val==1100000&&!strcmp(votes[1].client,USER_DAEMON_VOTER));
 assert(!disable_chg_read(chg,&v)&&v==3);nvotes=0;assert(!disable_chg_write(chg,3)&&nvotes==0);
 nvotes=0;assert(!disable_chg_write(chg,2)&&nvotes==2&&votes[1].val==500000);
 nvotes=0;assert(!disable_chg_write(chg,1)&&nvotes==2&&votes[0].v==&fcc&&!votes[0].en&&votes[1].v==&dis&&votes[1].en==1);
 vote_rc=-EIO;assert(disable_chg_write(chg,0)==-EIO);vote_rc=0;
 /* --- debugfs nodes --- */
 smb5_create_debugfs(&chip);
 struct dentry *root=find("qpnp-smbcharger");assert(root&&chip.dfs_root==root);
 struct dentry *cl=find("otg_current_limit"),*od=find("otg_disable"),*dc=find("disable_chg");
 assert(cl&&od&&dc&&cl->parent==root&&od->parent==root);
 assert((cl->mode&07777)==0666&&(od->mode&07777)==0666&&cl->data==&chip&&od->data==&chip);
 const struct debugfs_ops *clo=cl->fops,*odo=od->fops;
 assert(clo->get==otg_current_limit_read&&clo->set==otg_current_limit_write&&!strcmp(clo->fmt,"0x%02llx\n"));
 assert(odo->get==otg_disable_read&&odo->set==otg_disable_write&&!strcmp(odo->fmt,"0x%02llx\n"));
 /* the handlers really get the chip pointer the file was created with */
 assert(!clo->get(cl->data,&v)&&v==1500000);
 assert(find("force_batt_psy_update")&&find("debug_mask"));
 ndents=0;logs=0;fail_create=1;smb5_create_debugfs(&chip);assert(logs==1&&find("otg_current_limit"));fail_create=0;
 puts("PASS: otg_current_limit accepts exactly 500000/1000000/1500000 uA, writes PMIC only on change, keeps readback on failure; "
      "otg_disable reads OTG_EN_BIT of DCDC_CMD_OTG_REG and only accepts 0; disable_chg step 3 votes 1100 mA; "
      "debugfs names, 0666 modes, fops and chip data");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    srcs={n:(SOURCE/n).read_text() for n in (SMB,REG)}
    defs='\n'.join(l for l in srcs[REG].splitlines() if re.match(r'#define (DCDC_BASE|DCDC_CMD_OTG_REG|OTG_EN_BIT)\s',l))
    smb=srcs[SMB]
    pieces=[]
    for f,s in FUNCS:
        body=ex.function(smb,s);pieces.append(body)
        # keep the DEFINE_DEBUGFS_ATTRIBUTE that follows each handler pair
        end=smb.index(body)+len(body);m=re.match(r'\s*(DEFINE_DEBUGFS_ATTRIBUTE\([^;]*;)',smb[end:],re.S)
        if m:pieces.append(m.group(1))
        if s.startswith('static int disable_chg_write('):pieces.insert(len(pieces)-1,'static int pico_val = 0;')
    expected={'EXP_CMD_OTG':0x1140,'EXP_OTG_CL_REG':0x1152,'EXP_DEFAULT_CL':1500000}
    head=''.join(f'#define {k} {v}\n' for k,v in expected.items())
    code=MODEL+defs+'\n'+head+'\n'.join(pieces)+'\n'+MAIN
    out=BASE/'out/phoenix-kernel-recovery/smb5-otg-debugfs-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in sorted(srcs)},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'expected':expected,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual otg_current_limit/otg_disable get/set handlers, their DEFINE_DEBUGFS_ATTRIBUTE fops, disable_chg_write/read and '
                    'smb5_create_debugfs. PMIC registers, charge-param programming, votables and debugfs modeled; the register address '
                    '0x1140 (DCDC_CMD_OTG_REG) and the accepted current set come from the factory decompile, not from the patch.',
            'device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
