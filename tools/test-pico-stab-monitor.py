"""Execute the actual stab_monitor (/dev/stabd) and f2fs core-file reserve bodies under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
DRV='drivers/misc/stab_monitor.c';F2H='fs/f2fs/f2fs.h';NAMEI='fs/f2fs/namei.c'
DRV_FUNCS=['bool is_core_file_name(','static ssize_t stabd_read(','static ssize_t stabd_write(','static __poll_t stabd_poll(',
           'static long stabd_add_core_name(','static long stabd_mark_core_file(','static long stabd_ioctl(','static void __exit stab_mod_exit(']
F2_FUNCS=[(F2H,'static inline bool __allow_reserved_blocks('),(F2H,'static inline bool f2fs_core_file_name('),(F2H,'static inline void f2fs_mark_core_file('),
          (F2H,'static inline bool f2fs_is_core_file('),(F2H,'static inline int inc_valid_block_count('),(F2H,'static inline int inc_valid_node_count('),
          (NAMEI,'static void f2fs_check_core_file_create(')]
MODEL=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;typedef unsigned int __poll_t;typedef u32 block_t;typedef unsigned short umode_t;
#define BIT(n) (1UL<<(n))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define READ_ONCE(x) (x)
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define unlikely(x) (x)
#define __user
#define __exit
#define EXPORT_SYMBOL_GPL(x)
#define module_param(a,b,c)
#define EPERM 1
#define ENOMEM 12
#define EFAULT 14
#define ENOSPC 28
#define ENOTTY 25
#define ENOENT 2
#define ERESTARTSYS 512
#define EPOLLIN 0x1
#define EPOLLRDNORM 0x40
#define O_RDONLY 0
#define O_RDWR 2
#define O_CREAT 0100
#define O_NONBLOCK 04000
#define FMODE_READ 1
#define FMODE_WRITE 2
#define TASK_COMM_LEN 16
#define GFP_KERNEL 0
#define S_IFREG 0100000
#define S_IFDIR 0040000
#define S_ISREG(m) (((m)&0170000)==S_IFREG)
#define _IOW(t,nr,sz) ((1U<<30)|((unsigned)sizeof(sz)<<16)|((unsigned)(t)<<8)|(nr))
#define IS_ERR(p) ((unsigned long)(p)>=(unsigned long)-4095)
#define ERR_PTR(e) ((void *)(long)(e))
static int infos,errs;
#define pr_info(...) (infos++)
#define pr_err(...) (errs++)
/* atomic-context tracking: sleeping calls must not run under a spinlock */
static int atomic_depth;
static void might_sleep(void){assert(atomic_depth==0);}
typedef struct {int held;const char *name;int order;} spinlock_t;
/* ordered spinlocks (stat_lock 1 < i_lock 2 < d_lock 3) must nest upwards */
static int held_orders[8],nheld;
static void spin_lock(spinlock_t *l){assert(!l->held);if(l->order)for(int k=0;k<nheld;k++)assert(held_orders[k]<l->order);
  l->held=1;atomic_depth++;if(l->order)held_orders[nheld++]=l->order;}
static void spin_unlock(spinlock_t *l){assert(l->held);l->held=0;atomic_depth--;
  if(l->order){int k;for(k=0;k<nheld&&held_orders[k]!=l->order;k++);assert(k<nheld);for(;k<nheld-1;k++)held_orders[k]=held_orders[k+1];nheld--;}}
typedef struct {int readers,writer;} rwlock_t;
static void read_lock(rwlock_t *l){assert(!l->writer);l->readers++;atomic_depth++;}
static void read_unlock(rwlock_t *l){assert(l->readers>0);l->readers--;atomic_depth--;}
static void write_lock(rwlock_t *l){assert(!l->writer&&!l->readers);l->writer=1;atomic_depth++;}
static void write_unlock(rwlock_t *l){assert(l->writer);l->writer=0;atomic_depth--;}
struct mutex {int held;};
static void mutex_lock(struct mutex *m){might_sleep();assert(!m->held);m->held=1;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=0;}
#define DEFINE_MUTEX(n) struct mutex n={0}
#define DEFINE_RWLOCK(n) rwlock_t n={0,0}
struct list_head {struct list_head *next,*prev;};
#define LIST_HEAD(n) struct list_head n={&(n),&(n)}
static void list_add(struct list_head *n,struct list_head *h){n->next=h->next;n->prev=h;h->next->prev=n;h->next=n;}
static void list_add_tail(struct list_head *n,struct list_head *h){n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;}
static void list_del(struct list_head *e){e->prev->next=e->next;e->next->prev=e->prev;e->next=(void *)0xdead000000000100UL;e->prev=(void *)0xdead000000000200UL;}
#define list_entry(p,t,m) container_of(p,t,m)
#define list_first_entry_or_null(h,t,m) ((h)->next!=(h)?list_entry((h)->next,t,m):NULL)
#define list_for_each_entry(p,h,m) for(p=list_entry((h)->next,__typeof__(*p),m);&p->m!=(h);p=list_entry(p->m.next,__typeof__(*p),m))
#define list_for_each_entry_safe(p,n,h,m) for(p=list_entry((h)->next,__typeof__(*p),m),n=list_entry(p->m.next,__typeof__(*p),m);&p->m!=(h);p=n,n=list_entry(n->m.next,__typeof__(*n),m))
struct hlist_node {struct hlist_node *next,**pprev;};struct hlist_head {struct hlist_node *first;};
#define hlist_entry_safe(p,t,m) ((p)?container_of(p,t,m):NULL)
#define hlist_for_each_entry(p,h,m) for(p=hlist_entry_safe((h)->first,__typeof__(*p),m);p;p=hlist_entry_safe(p->m.next,__typeof__(*p),m))
/* wait queues */
typedef struct {int wakes,poll_wakes,poll_regs;unsigned last_key;} wait_queue_head_t;
#define DECLARE_WAIT_QUEUE_HEAD(n) wait_queue_head_t n={0}
static int wait_interrupt;static void (*wait_producer)(void);static int waits;
#define wait_event_interruptible(wq,cond) ({int __r=0;waits++;might_sleep();if(!(cond)){if(wait_producer){wait_producer();wait_producer=NULL;}if(!(cond)){assert(wait_interrupt);__r=-ERESTARTSYS;}}__r;})
static void wake_up_interruptible(wait_queue_head_t *q){q->wakes++;}
static void wake_up_interruptible_poll(wait_queue_head_t *q,unsigned k){q->poll_wakes++;q->last_key=k;}
typedef struct {int x;} poll_table;
struct file;
static void poll_wait(struct file *f,wait_queue_head_t *q,poll_table *p){(void)f;(void)p;q->poll_regs++;}
/* tasks */
struct task_struct {char comm[TASK_COMM_LEN];int pid,tgid;struct task_struct *group_leader;};
static struct task_struct leader={"stabd",100,100,&leader},thread={"binder:100_2",101,100,&leader},*current=&thread;
static void get_task_comm(char *b,struct task_struct *t){memcpy(b,t->comm,TASK_COMM_LEN);}
/* memory and user copies */
static int allocs,alloc_fail;
static void *kzalloc(size_t n,int f){(void)f;might_sleep();if(alloc_fail){alloc_fail--;return NULL;}allocs++;return calloc(1,n);}
static void kfree(const void *p){if(p)allocs--;free((void *)p);}
static int uaccess_fault;
static unsigned long copy_to_user(void *d,const void *s,unsigned long n){might_sleep();if(uaccess_fault)return n;memcpy(d,s,n);return 0;}
static unsigned long copy_from_user(void *d,const void *s,unsigned long n){might_sleep();if(uaccess_fault)return n;memcpy(d,s,n);return 0;}
/* vfs */
struct inode;
struct qstr {u32 len;const unsigned char *name;};
struct dentry {spinlock_t d_lock;struct qstr d_name;union {struct hlist_node d_alias;} d_u;struct inode *d_inode;};
typedef struct {unsigned val;} kuid_t;typedef struct {unsigned val;} kgid_t;
#define __kuid_val(u) ((u).val)
struct inode {umode_t i_mode;unsigned short i_opflags;kuid_t i_uid;unsigned i_flags;spinlock_t i_lock;struct hlist_head i_dentry;unsigned long i_ino;};
struct file {unsigned f_flags;unsigned f_mode;struct inode *f_inode;};
static struct inode *file_inode(struct file *f){return f->f_inode;}
static struct file open_file;static struct inode open_inode;static int open_err,opens,closes,open_flags,open_mode;static char open_path[256];
static struct file *filp_open(const char *p,int fl,int mode){might_sleep();opens++;strncpy(open_path,p,255);open_flags=fl;open_mode=mode;if(open_err)return ERR_PTR(open_err);open_file.f_inode=&open_inode;return &open_file;}
static int filp_close(struct file *f,void *id){(void)id;assert(f==&open_file);closes++;return 0;}
static int misc_deregistered;struct miscdevice {int x;};static struct miscdevice stab_misc_device;
static void misc_deregister(struct miscdevice *m){(void)m;misc_deregistered++;}
'''
F2MODEL=r'''
/* f2fs model */
#define F2FS_MOUNT_RESERVE_ROOT 1
#define SBI_CP_DISABLED 3
#define CAP_SYS_RESOURCE 24
struct f2fs_mount_info {unsigned opt;block_t root_reserved_blocks;kuid_t s_resuid;kgid_t s_resgid;};
struct f2fs_sb_info {spinlock_t stat_lock;block_t user_block_count,total_valid_block_count,current_reserved_blocks,core_files_reserved_blocks,unusable_block_count;
  unsigned total_valid_node_count,total_node_count;struct f2fs_mount_info mount_opt;unsigned long s_flag;long alloc_valid_block_count;};
#define F2FS_OPTION(sbi) ((sbi)->mount_opt)
#define test_opt(sbi,o) (F2FS_OPTION(sbi).opt&F2FS_MOUNT_##o)
static bool is_sbi_flag_set(struct f2fs_sb_info *s,unsigned t){return s->s_flag&(1UL<<t);}
#define IS_NOQUOTA(i) ((i)->i_flags&32)
static kuid_t cur_fsuid={10000};static kuid_t current_fsuid(void){return cur_fsuid;}
#define uid_eq(a,b) ((a).val==(b).val)
#define gid_eq(a,b) ((a).val==(b).val)
static const kgid_t GLOBAL_ROOT_GID={0};
static int in_group_p(kgid_t g){(void)g;return 0;}
static int cap_sys_resource;static int capable(int c){assert(c==CAP_SYS_RESOURCE);return cap_sys_resource;}
static bool time_to_inject(struct f2fs_sb_info *s,int t){(void)s;(void)t;return false;}
#define FAULT_BLOCK 0
#define f2fs_show_injection_info(t) ((void)0)
static long dq_reserved,dq_inodes;
static int dquot_reserve_block(struct inode *i,blkcnt_t n){(void)i;dq_reserved+=n;return 0;}
static void dquot_release_reservation_block(struct inode *i,blkcnt_t n){(void)i;dq_reserved-=n;}
static int dquot_alloc_inode(struct inode *i){(void)i;dq_inodes++;return 0;}
static void dquot_free_inode(struct inode *i){(void)i;dq_inodes--;}
static void percpu_counter_add(long *c,long n){*c+=n;}
static void percpu_counter_sub(long *c,long n){*c-=n;}
static void percpu_counter_inc(long *c){(*c)++;}
static long iblocks;static void f2fs_i_blocks_write(struct inode *i,block_t n,bool a,bool b){(void)i;(void)a;(void)b;iblocks+=n;}
static void f2fs_mark_inode_dirty_sync(struct inode *i,bool s){(void)i;(void)s;}
'''
MAIN=r'''
#define CORE_NAME(s) do{char n[60]={0};strncpy(n,s,59);assert(stabd_ioctl(&rw_file,STABD_IOC_ADD_CORE_NAME,(unsigned long)n)==0);}while(0)
static struct file rw_file={0,FMODE_READ|FMODE_WRITE,NULL},nb_file={O_NONBLOCK,FMODE_READ|FMODE_WRITE,NULL},wo_file={0,FMODE_WRITE,NULL};
static int calls_core;
static void produce_one(void){struct stabd_block_logo l={7,77};assert(stabd_write(&nb_file,(const char *)&l,sizeof(l),NULL)==8);}
static struct f2fs_sb_info sbi;
static void reset_sbi(block_t user,block_t total,block_t core){memset(&sbi,0,sizeof(sbi));sbi.stat_lock.order=1;sbi.user_block_count=user;sbi.total_valid_block_count=total;
  sbi.core_files_reserved_blocks=core;sbi.total_node_count=1000000;}
static void mk_inode(struct inode *i,struct dentry *d,const char *name,unsigned uid,umode_t mode){memset(i,0,sizeof(*i));memset(d,0,sizeof(*d));
  i->i_mode=mode;i->i_uid.val=uid;i->i_lock.order=2;d->d_lock.order=3;i->i_ino=42;
  if(name){d->d_name.name=(const unsigned char *)name;d->d_name.len=strlen(name);d->d_inode=i;i->i_dentry.first=&d->d_u.d_alias;d->d_u.d_alias.pprev=&i->i_dentry.first;}}
int main(void){char buf[64];struct stabd_block_logo logo;int i;
 assert(STABD_IOC_MARK_CORE_FILE==0x40cc6401&&STABD_IOC_ADD_CORE_NAME==0x403c6402&&STABD_IOC_SEAL_CORE_NAMES==0x40046403);
 assert(stabd_ioctl(&rw_file,0x1234,0)==-ENOTTY);
 /* --- core name list --- */
 assert(!is_core_file_name("settings_secure.xml",19));
 CORE_NAME("settings_secure.xml");CORE_NAME("locksettings.db");CORE_NAME("notification_log.db-wal");CORE_NAME("settings.json");CORE_NAME("update_log.txt");
 assert(is_core_file_name("settings_secure.xml",19)&&is_core_file_name("locksettings.db",15)&&!is_core_file_name("settings_secure.xm",18));
 {char longname[60];memset(longname,'a',60);assert(stabd_ioctl(&rw_file,STABD_IOC_ADD_CORE_NAME,(unsigned long)longname)==0);
  char t59[60];memset(t59,'a',59);t59[59]=0;assert(is_core_file_name(t59,59));}
 uaccess_fault=1;{char n[60]="x.xml";int a=allocs;assert(stabd_ioctl(&rw_file,STABD_IOC_ADD_CORE_NAME,(unsigned long)n)==-EFAULT&&allocs==a);}uaccess_fault=0;
 alloc_fail=1;{char n[60]="y.xml";assert(stabd_ioctl(&rw_file,STABD_IOC_ADD_CORE_NAME,(unsigned long)n)==-ENOMEM);}
 {unsigned saved=core_names_num;core_names_num=STABD_MAX_CORE_NAMES;char n[60]="z.xml";int a=allocs;assert(stabd_ioctl(&rw_file,STABD_IOC_ADD_CORE_NAME,(unsigned long)n)==-ENOSPC&&allocs==a);core_names_num=saved;}
 /* --- f2fs name filter --- */
 assert(f2fs_core_file_name("settings_secure.xml")&&f2fs_core_file_name("locksettings.db")&&f2fs_core_file_name("notification_log.db-wal")&&f2fs_core_file_name("update_log.txt"));
 assert(!f2fs_core_file_name("settings.json")&&!f2fs_core_file_name("other.xml")&&!f2fs_core_file_name("db")&&!f2fs_core_file_name("xdb"));
 {char t59[60];memset(t59,'a',59);t59[59]=0;assert(!f2fs_core_file_name(t59));memcpy(t59+56,"xml",3);CORE_NAME(t59);assert(f2fs_core_file_name(t59));
  char t60[61];memset(t60,'a',60);memcpy(t60+57,"xml",3);t60[60]=0;assert(!f2fs_core_file_name(t60));}
 /* --- seal: further names are ignored --- */
 assert(stabd_ioctl(&rw_file,STABD_IOC_SEAL_CORE_NAMES,0)==0);{int a=allocs;CORE_NAME("late.xml");assert(!is_core_file_name("late.xml",8)&&allocs==a);}
 /* --- write path --- */
 assert(stabd_write(&rw_file,"12345",5,NULL)==-EFAULT);
 logo=(struct stabd_block_logo){16,1};{int a=allocs;assert(stabd_write(&rw_file,(const char *)&logo,8,NULL)==-EFAULT&&allocs==a);}
 uaccess_fault=1;logo=(struct stabd_block_logo){1,1};{int a=allocs;assert(stabd_write(&rw_file,(const char *)&logo,8,NULL)==-EFAULT&&allocs==a);}uaccess_fault=0;
 alloc_fail=1;assert(stabd_write(&rw_file,(const char *)&logo,8,NULL)==-ENOMEM);
 for(i=0;i<STABD_MAX_EVENTS;i++){logo=(struct stabd_block_logo){(u32)(i%16),(u32)(1000+i)};assert(stabd_write(i&1?&nb_file:&rw_file,(const char *)&logo,8,NULL)==8);}
 /* every write wakes readers and pollers, also from a non-blocking writer */
 assert(stabd_wq.wakes==STABD_MAX_EVENTS&&stabd_wq2.poll_wakes==STABD_MAX_EVENTS&&stabd_wq2.last_key==EPOLLIN);
 {int a=allocs;assert(stabd_write(&rw_file,(const char *)&logo,8,NULL)==-EPERM&&allocs==a&&stabd_list_num==STABD_MAX_EVENTS);}
 /* --- poll --- */
 {poll_table pt;assert(stabd_poll(&rw_file,&pt)==(EPOLLIN|EPOLLRDNORM)&&stabd_poll(&wo_file,&pt)==0&&stabd_wq2.poll_regs==2);}
 /* --- read path: only the stabd process, FIFO, zero-padded to 24 bytes --- */
 strcpy(leader.comm,"system_server");assert(stabd_read(&rw_file,buf,64,NULL)==-EPERM&&stabd_list_num==STABD_MAX_EVENTS);strcpy(leader.comm,"stabd");
 memset(buf,0xcc,sizeof(buf));assert(stabd_read(&rw_file,buf,64,NULL)==24);
 {u32 v[2];memcpy(v,buf,8);assert(v[0]==0&&v[1]==1000);for(i=8;i<24;i++)assert(buf[i]==0);assert((u8)buf[24]==0xcc);}
 assert(stabd_read(&rw_file,buf,8,NULL)==8);{u32 v[2];memcpy(v,buf,8);assert(v[0]==1&&v[1]==1001);}
 assert(stabd_read(&rw_file,buf,4,NULL)==4);{u32 v;memcpy(&v,buf,4);assert(v==2);}
 uaccess_fault=1;{int n=stabd_list_num,a=allocs;assert(stabd_read(&rw_file,buf,8,NULL)==-EFAULT&&stabd_list_num==n-1&&allocs==a-1);}uaccess_fault=0;
 while(stabd_list_num){assert(stabd_read(&nb_file,buf,8,NULL)==8);}
 {poll_table pt;assert(stabd_poll(&rw_file,&pt)==0);}
 assert(stabd_read(&nb_file,buf,8,NULL)==0);
 /* blocking reader: woken by a writer; an interrupted wait reads nothing */
 wait_producer=produce_one;assert(stabd_read(&rw_file,buf,8,NULL)==8);{u32 v[2];memcpy(v,buf,8);assert(v[0]==7&&v[1]==77);}
 wait_interrupt=1;assert(stabd_read(&rw_file,buf,8,NULL)==0);wait_interrupt=0;
 /* --- mark ioctl --- */
 {struct stabd_core_file_mark m;memset(&m,'p',sizeof(m));m.flags=STABD_MARK_RDONLY;open_inode.i_lock.order=2;
  assert(stabd_ioctl(&rw_file,STABD_IOC_MARK_CORE_FILE,(unsigned long)&m)==0&&open_flags==O_RDONLY&&strlen(open_path)==STABD_PATH_LEN-1&&(open_inode.i_opflags&IOP_PICO_CORE_FILE)&&closes==1);
  open_inode.i_opflags=0;memset(&m,0,sizeof(m));strcpy(m.path,"/data/system/users/0/settings_secure.xml");
  assert(stabd_ioctl(&rw_file,STABD_IOC_MARK_CORE_FILE,(unsigned long)&m)==0&&open_flags==(O_RDWR|O_CREAT)&&open_mode==0&&!strcmp(open_path,m.path)&&(open_inode.i_opflags&IOP_PICO_CORE_FILE));
  open_inode.i_opflags=0;open_err=-ENOENT;assert(stabd_ioctl(&rw_file,STABD_IOC_MARK_CORE_FILE,(unsigned long)&m)==0&&!open_inode.i_opflags&&closes==2);open_err=0;
  uaccess_fault=1;int o=opens;assert(stabd_ioctl(&rw_file,STABD_IOC_MARK_CORE_FILE,(unsigned long)&m)==-EFAULT&&opens==o);uaccess_fault=0;}
 /* --- f2fs: core file detection --- */
 {struct inode in;struct dentry de;
  reset_sbi(1000,0,50);
  assert(!f2fs_is_core_file(NULL));
  mk_inode(&in,&de,"settings_secure.xml",1000,S_IFREG|0600);spin_lock(&sbi.stat_lock);assert(f2fs_is_core_file(&in));spin_unlock(&sbi.stat_lock);assert(in.i_opflags&IOP_PICO_CORE_FILE);
  de.d_name.name=(const unsigned char *)"renamed.bin";de.d_name.len=11;assert(f2fs_is_core_file(&in));
  mk_inode(&in,&de,"settings_secure.xml",10050,S_IFREG|0600);assert(!f2fs_is_core_file(&in));
  mk_inode(&in,&de,"settings_secure.xml",0,S_IFDIR|0700);assert(!f2fs_is_core_file(&in));
  mk_inode(&in,&de,NULL,0,S_IFREG|0600);assert(!f2fs_is_core_file(&in));
  mk_inode(&in,&de,"other.xml",0,S_IFREG|0600);assert(!f2fs_is_core_file(&in)&&!in.i_opflags);
  mk_inode(&in,&de,"locksettings.db",0,S_IFREG|0600);assert(f2fs_is_core_file(&in));}
 /* --- inc_valid_block_count --- */
 {struct inode core,plain;struct dentry dc,dp;blkcnt_t cnt;
  mk_inode(&core,&dc,"locksettings.db",1000,S_IFREG|0600);mk_inode(&plain,&dp,"cache.bin",10050,S_IFREG|0600);
  reset_sbi(1000,900,50);cnt=30;assert(!inc_valid_block_count(&sbi,&plain,&cnt)&&cnt==30&&sbi.total_valid_block_count==930&&!core.i_opflags);
  cnt=30;assert(!inc_valid_block_count(&sbi,&plain,&cnt)&&cnt==20&&sbi.total_valid_block_count==950&&dq_reserved==50);
  cnt=5;assert(inc_valid_block_count(&sbi,&plain,&cnt)==-ENOSPC&&sbi.total_valid_block_count==950&&dq_reserved==50);
  cnt=40;assert(!inc_valid_block_count(&sbi,&core,&cnt)&&cnt==40&&sbi.total_valid_block_count==990&&(core.i_opflags&IOP_PICO_CORE_FILE));
  cnt=20;assert(!inc_valid_block_count(&sbi,&core,&cnt)&&cnt==10&&sbi.total_valid_block_count==1000);
  /* feature off: no reserve, nothing flagged */
  mk_inode(&core,&dc,"locksettings.db",1000,S_IFREG|0600);reset_sbi(1000,900,0);cnt=100;assert(!inc_valid_block_count(&sbi,&plain,&cnt)&&cnt==100&&!core.i_opflags);
  /* the core reserve stacks with current_reserved_blocks and root reserve */
  reset_sbi(1000,800,50);sbi.current_reserved_blocks=100;sbi.mount_opt.opt=F2FS_MOUNT_RESERVE_ROOT;sbi.mount_opt.root_reserved_blocks=20;
  cnt=40;assert(!inc_valid_block_count(&sbi,&plain,&cnt)&&cnt==30&&sbi.total_valid_block_count==830);
  cnt=40;assert(!inc_valid_block_count(&sbi,&core,&cnt)&&cnt==40&&sbi.total_valid_block_count==870);
  /* CAP_SYS_RESOURCE opens the root reserve but never the core file reserve */
  reset_sbi(1000,800,50);sbi.current_reserved_blocks=100;sbi.mount_opt.opt=F2FS_MOUNT_RESERVE_ROOT;sbi.mount_opt.root_reserved_blocks=20;cap_sys_resource=1;
  cnt=40;assert(!inc_valid_block_count(&sbi,&plain,&cnt)&&cnt==40&&sbi.total_valid_block_count==840);
  cnt=40;assert(!inc_valid_block_count(&sbi,&plain,&cnt)&&cnt==10&&sbi.total_valid_block_count==850);cap_sys_resource=0;}
 /* --- inc_valid_node_count --- */
 {struct inode core,plain;struct dentry dc,dp;
  mk_inode(&core,&dc,"settings_secure.xml",1000,S_IFREG|0600);mk_inode(&plain,&dp,"cache.bin",10050,S_IFREG|0600);
  reset_sbi(1000,949,50);assert(!inc_valid_node_count(&sbi,&plain,false)&&sbi.total_valid_block_count==950);
  assert(inc_valid_node_count(&sbi,&plain,false)==-ENOSPC&&sbi.total_valid_block_count==950);
  assert(!inc_valid_node_count(&sbi,&core,false)&&sbi.total_valid_block_count==951);
  /* recovery passes no inode: no dereference, the reserve stays closed */
  assert(inc_valid_node_count(&sbi,NULL,true)==-ENOSPC);
  reset_sbi(1000,100,50);assert(!inc_valid_node_count(&sbi,NULL,true)&&sbi.total_valid_node_count==1);}
 /* --- f2fs_create flags registered names once the reserve is reached --- */
 {struct inode in;struct dentry de;
  mk_inode(&in,&de,"settings_secure.xml",1000,S_IFREG|0600);reset_sbi(1000,900,50);f2fs_check_core_file_create(&sbi,&in,&de);assert(!in.i_opflags);
  reset_sbi(1000,949,50);f2fs_check_core_file_create(&sbi,&in,&de);assert(in.i_opflags&IOP_PICO_CORE_FILE);
  mk_inode(&in,&de,"cache.xml",1000,S_IFREG|0600);f2fs_check_core_file_create(&sbi,&in,&de);assert(!in.i_opflags);
  mk_inode(&in,&de,"settings_secure.xml",1000,S_IFREG|0600);reset_sbi(1000,948,50);f2fs_check_core_file_create(&sbi,&in,&de);assert(!in.i_opflags);
  sbi.s_flag=1UL<<SBI_CP_DISABLED;sbi.unusable_block_count=1;f2fs_check_core_file_create(&sbi,&in,&de);assert(in.i_opflags);}
 assert(atomic_depth==0);
 stab_mod_exit();assert(misc_deregistered==1&&allocs==0&&stabd_list_num==0&&core_names_num==0);
 puts("PASS: ioctl numbers; core name register/seal/cap/fault/alloc failure/truncation; f2fs suffix filter and 59-char limit; "
      "block-logo write validation, 50-entry cap, wakeups from non-blocking writers; poll readiness; read restricted to the stabd "
      "process, FIFO, zero padding to 24 bytes, faults, blocking/interrupted waits; mark ioctl open modes and failures; core inode "
      "detection (uid, type, alias, cached flag); inc_valid_block_count/inc_valid_node_count reserve accounting incl. NULL-inode "
      "recovery; create-time flagging; no sleeping under spinlocks; exit frees everything");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    drv=(SOURCE/DRV).read_text();f2h=(SOURCE/F2H).read_text();namei=(SOURCE/NAMEI).read_text()
    top=drv[drv.index('#define STABD_MAX_EVENTS'):drv.index('bool is_core_file_name(')]
    stab_h=(SOURCE/'include/linux/stab_monitor.h').read_text()
    iop=[l for l in stab_h.splitlines() if l.startswith('#define IOP_PICO_CORE_FILE')][0]
    srcs={F2H:f2h,NAMEI:namei}
    code=(MODEL+iop+'\n'+top+'\n'.join(ex.function(drv,f) for f in DRV_FUNCS)+'\n'+F2MODEL
          +'\n'.join(ex.function(srcs[f],s) for f,s in F2_FUNCS)+MAIN)
    out=BASE/'out/phoenix-kernel-recovery/stab-monitor-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-Wno-pointer-sign','-Wno-unused-variable','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    names=[DRV,F2H,NAMEI,'include/linux/stab_monitor.h']
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in names},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual stab_monitor read/write/poll/ioctl/add/mark/exit and is_core_file_name, f2fs __allow_reserved_blocks, core name filter, '
                    'core inode detection, inc_valid_block_count, inc_valid_node_count and f2fs_check_core_file_create. VFS, uaccess, wait queues, '
                    'locks (with lock order stat_lock > i_lock > d_lock and no sleeping under spinlocks) modeled. statfs and sysfs store compiled only.',
            'device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
