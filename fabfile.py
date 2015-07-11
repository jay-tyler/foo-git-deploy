from fabric.api import run
from fabric.api import env
import boto.ec2
import time
from fabric.api import prompt
from fabric.api import execute
from fabric.api import sudo, local
from fabric.contrib import files


env.hosts = ['localhost', ]
env.aws_region = 'us-west-2'
env.ssh_key_path = '~/.ssh/pk-aws.pem'
PATH_TO_SUPRCONF = "/etc/supervisor/supervisord.conf"


def host_type():
    run('uname -s')


def get_ec2_connection():
    if 'ec2' not in env:
        conn = boto.ec2.connect_to_region(env.aws_region)
        if conn is not None:
            env.ec2 = conn
            print "Connected to EC2 region %s" % env.aws_region
        else:
            msg = "Unable to connect to EC2 region %s" % env.aws_region
            raise IOError(msg % env.aws_region)
    return env.ec2


def provision_instance(wait_for_running=True, timeout=60, interval=2):
    wait_val = int(interval)
    timeout_val = int(timeout)
    conn = get_ec2_connection()
    instance_type = 't1.micro'
    key_name = 'jason.tyler'
    security_group = 'ssh-access'
    image_id = 'ami-d0d8b8e0'

    reservations = conn.run_instances(
        image_id,
        key_name=key_name,
        instance_type=instance_type,
        security_groups=[security_group, ]
    )
    new_instances = [i for i in reservations.instances if i.state == u'pending']
    running_instance = []
    if wait_for_running:
        waited = 0
        while new_instances and (waited < timeout_val):
            time.sleep(wait_val)
            waited += int(wait_val)
            for instance in new_instances:
                state = instance.state
                print "Instance %s is %s" % (instance.id, state)
                if state == "running":
                    running_instance.append(
                        new_instances.pop(new_instances.index(i))
                    )
                instance.update()


def list_aws_instances(verbose=False, state='all'):
    conn = get_ec2_connection()

    reservations = conn.get_all_reservations()
    instances = []
    for res in reservations:
        for instance in res.instances:
            if state == 'all' or instance.state == state:
                instance = {
                    'id': instance.id,
                    'type': instance.instance_type,
                    'image': instance.image_id,
                    'state': instance.state,
                    'instance': instance,
                }
                instances.append(instance)
    env.instances = instances
    if verbose:
        import pprint
        pprint.pprint(env.instances)


def select_instance(state='running'):
    if env.get('active_instance', False):
        return

    list_aws_instances(state=state)

    prompt_text = "Please select from the following instances:\n"
    instance_template = " %(ct)d: %(state)s instance %(id)s\n"
    for idx, instance in enumerate(env.instances):
        ct = idx + 1
        args = {'ct': ct}
        args.update(instance)
        prompt_text += instance_template % args
    prompt_text += "Choose an instance: "

    def validation(input):
        choice = int(input)
        if choice not in range(1, len(env.instances) + 1):
            raise ValueError("%d is not a valid instance" % choice)
        return choice

    choice = prompt(prompt_text, validate=validation)
    env.active_instance = env.instances[choice - 1]['instance']


def get_selected_hosts(string=False):
    selected_hosts = [
        'ubuntu@' + env.active_instance.public_dns_name
    ]
    if not string:
        return selected_hosts
    else:
        #  This block currently serving copy_single_file() and
        #  copy_single_dir()
        return str(selected_hosts[0])


def run_command_on_selected_server(command):
    select_instance()
    execute(command, hosts=get_selected_hosts())


def install_pip():
    def _install_pip():
        sudo('apt-get install -y python-pip')
    run_command_on_selected_server(_install_pip)


def install_supervisor():
    def _install_supervisor():
        sudo('apt-get install -y supervisor')
    run_command_on_selected_server(_install_supervisor)


def setup_supervisor(app_name):
    """Appends python application information to the supervisor conf file;
    expects the application to be in a self-named directory in home dir"""
    def _setup_supervisor():
        conf_text_lst = ["[program:{app_name}]",
                         "command: /usr/bin/python -m {app_name}",
                         "directory: /home/ubuntu/{app_name}",
                         "autostart: true"]
        conf_text = "\n".join(conf_text_lst).format(app_name=app_name)
        files.append(PATH_TO_SUPRCONF, conf_text, use_sudo=True)
    run_command_on_selected_server(_setup_supervisor)


def start_supervisor():
    def _start_supervisor():
        sudo('service supervisor start')

    run_command_on_selected_server(_start_supervisor)


def restart_supervisor(app_name):
    def _restart_supervisor():
        sudo('supervisorctl restart {app_name}'.format(app_name=app_name))

    run_command_on_selected_server(_restart_supervisor)


def install_nginx():

    def _install_nginx():
        sudo('apt-get update')
        sudo('apt-get install -y nginx')
        sudo('/etc/init.d/nginx start')

    run_command_on_selected_server(_install_nginx)


def execute_setup_py(app_name=None):

    def _execute_setup_py():
        sudo('sudo python ~/{app_name}/setup.py install'.format(
             app_name=app_name))
        sudo('sudo python ~/{app_name}/setup.py clean --all'.format(
             app_name=app_name))

    run_command_on_selected_server(_execute_setup_py)


def unlink_port():
    """Run this to free the port that supervisor needs access to"""
    def _unlink_port():
        sudo('sudo unlink /var/run/supervisor.sock')

    run_command_on_selected_server(_unlink_port)


def setup_nginx_conf():
    """"""
    def _setup_nginx_conf():

        app_conf_l = ['server {{',
        '    listen 80;'
        '    server_name http://{dns}/;',
        '    access_log  /var/log/nginx/test.log;\n',
        '    location / {{',
        '        proxy_pass http://127.0.0.1:8000;',
        '        proxy_set_header Host $host;',
        '        proxy_set_header X-Real-IP $remote_addr;',
        '        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;',
        '    }}']
        app_conf = '/n'.join(app_conf_l).format(
                   dns=env.active_instance.public_dns_name)

        # sudo('mv /etc/nginx/sites-available/default\
        #          /etc/nginx/sites-available/default.orig')
        # sudo('rm /etc/nginx/sites-available/default')
        sudo('touch /etc/nginx/sites-available/default')

    run_command_on_selected_server(_setup_nginx_conf)


def copy_single_file(file):
    command = ('scp -i ~/.ssh/pk-aws.pem {file} '.format(file=file) +
               get_selected_hosts(string=True) + ":~/")
    local(command)


def copy_single_dir(dir):
    command = ('scp -rp {dir} '.format(dir=dir) +
               get_selected_hosts(string=True) + ":~/")
    #  A little bit of a hack here, but the -i flag wasn't parsing correctly
    #  local('ssh-add ~/.ssh/pk-aws')
    local(command)


def deploy_local(new=False, dir=None, file=None, setup_py=True,
                 app_name=None):
    """Setup deployment from a local directory using server image id ami-d0d8b8e0
    Will setup a switch for future id's when the time comes.

    Use target directory as a self-named python application, which should
    include __init__.py and a properly formed setup.py
    """
    select_instance()
    if new:
        # install_nginx()
        install_pip()
        install_supervisor()
    if dir is not None:
        copy_single_dir(dir)
    if file is not None:
        copy_single_file(file)
    if setup_py and dir is not None:
        execute_setup_py(dir)
    if new:
        #  Block of things to do for new after installing Python stuff
        setup_supervisor(app_name)
        unlink_port()
        start_supervisor()
    elif app_name is not None:
        #  Run this block if not starting supervisor from scratch
        restart_supervisor(app_name)
    return

#  Fab file 