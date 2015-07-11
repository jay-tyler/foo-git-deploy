from fabric.api import run
from fabric.api import env
import boto.ec2
import time
from fabric.api import prompt
from fabric.api import execute
from fabric.api import sudo, local


env.hosts = ['localhost', ]
env.aws_region = 'us-west-2'
env.ssh_key_path = '~/.ssh/pk-aws.pem'


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
        #This block currently serving copy_single_file()
        return str(selected_hosts[0])
        print str(selected_hosts)


def run_command_on_selected_server(command):
    select_instance()
    # selected_hosts = [
    #     'ubuntu@' + env.active_instance.public_dns_name
    # ]
    execute(command, hosts=get_selected_hosts())


def install_pip():
    def _install_pip():
        sudo('apt-get install -y python-pip')
    run_command_on_selected_server(_install_pip)


def install_supervisor():

    def _install_supervisor():
        sudo('apt-get install -y supervisor')
    run_command_on_selected_server(_install_supervisor)


def install_nginx():

    def _install_nginx():
        sudo('apt-get update')
        sudo('apt-get install -y nginx')
        sudo('/etc/init.d/nginx start')

    run_command_on_selected_server(_install_nginx)


def execute_setup_py(dir=None):

    def _execute_setup_py(dir):
        try:
            pass
        except TypeError:
            pass


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


def deploy_local(new=False, dir=None, file=None, setup_py=True):
    if new:
        install_nginx()
        install_pip()
        install_supervisor()
    if dir is not None:
        copy_single_dir(dir)
    if file is not None:
        copy_single_file(file)
    if setup_py and dir is not None:
        execute_setup_py(dir)
    return

#  Need to append configuration bits to end of
# /etc/supervisor/supervisord.conf

# May need to run
# sudo unlink /var/run/supervisor.sock
# to get access to the port that runs when
# sudo service supervisor start

#  Then need to run the
#  sudo service start supervisor

#  Can check app status with
#  sudo supervisorctl status