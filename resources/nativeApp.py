#!/usr/bin/python -u

# Note that running python with the `-u` flag is required on Windows,
# in order to ensure that stdin and stdout are opened in binary, rather
# than text, mode.
import time
import json
import sys
import struct
import subprocess
import os
import signal
import logging
import shutil
import tarfile
from __future__ import print_function

# On Windows, the default I/O mode is O_TEXT. Set this to O_BINARY
# to avoid unwanted modifications of the input/output streams.
if sys.platform == "win32":
    import winreg
    import msvcrt
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

# global variables
# 'cwd' is for installtion file
cwd = os.path.dirname(os.path.realpath(sys.argv[0]))  # os.getcwd() may not correct if call it from outside(?)

# determine path of basedir
if sys.platform.startswith('linux'):
    basedir = os.path.expanduser("~/.config/Optract")
elif sys.platform.startswith('darwin'):
    basedir = os.path.expanduser("~/.config/Optract")
elif sys.platform.startswith('win32'):
    basedir = os.path.expanduser("~\AppData\Local\Optract")
if not os.path.isdir(basedir):
    os.mkdir(basedir)

lockFile = os.path.join(basedir, "dist", "Optract.LOCK")
myenv = os.environ.copy()  # "DLL initialize error..." in Windows while set the env inside subprocess calls
ipfs_path = os.path.join(basedir, 'ipfs_repo')
myenv['IPFS_PATH'] = ipfs_path

FNULL = open(os.devnull, 'w')
# ipfsP = None  # no need to be global
# nodeP = None

# logging
log_format = '[%(asctime)s] %(levelname)-7s : %(message)s'
log_datefmt = '%Y-%m-%d %H:%M:%S'
logfile = os.path.join(basedir, 'optract.log')
# replace the `filename=logfile` to `stream=sys.stdout` to direct log to stdout
logging.basicConfig(filename=logfile, level=logging.INFO, format=log_format,
                    datefmt=log_datefmt)


# Read a message from stdin and decode it.
def get_message():
    raw_length = sys.stdin.read(4)
    if not raw_length:
        sys.exit(0)
    message_length = struct.unpack('=I', raw_length)[0]  # python2
    # message_length = struct.unpack('=I', bytes(raw_length, encoding="utf-8"))[0]  # python3
    message = sys.stdin.read(message_length)
    return json.loads(message)


# Encode a message for transmission, given its content.
def encode_message(message_content):
    encoded_content = json.dumps(message_content)
    encoded_length = struct.pack('=I', len(encoded_content))  # python2
    # encoded_length = struct.pack('=I', len(encoded_content)).decode()  # python3
    return {'length': encoded_length, 'content': encoded_content}


# Send an encoded message to stdout.
def send_message(encoded_message):
    sys.stdout.write(encoded_message['length'])
    sys.stdout.write(encoded_message['content'])
    sys.stdout.flush()


def startServer():
    send_message(encode_message('in starting server'))
    if os.path.exists(lockFile):
        return

    ipfsConfigPath = os.path.join(basedir, "ipfs_repo", "config")
    ipfsBinPath = os.path.join(basedir, "dist", "bin", "ipfs")
    ipfsRepoPath = ipfs_path
    if not os.path.exists(ipfsConfigPath):
        send_message(encode_message('before init ipfs'))
        subprocess.check_call([ipfsBinPath, "init"], env=myenv, stdout=FNULL, stderr=subprocess.STDOUT)
        return startServer()
    else:
        send_message(encode_message('before starting ipfs'))
        ipfsP = subprocess.Popen([ipfsBinPath, "daemon", "--routing=dhtclient"], env=myenv, stdout=FNULL, stderr=subprocess.STDOUT)
        send_message(encode_message('after starting ipfs'))
    send_message(encode_message(' finish ipfs processing'))
    ipfsAPI = os.path.join(ipfsRepoPath, "api")
    ipfsLock = os.path.join(ipfsRepoPath, "repo.lock")
    while (not os.path.exists(ipfsAPI) or not os.path.exists(ipfsLock)):
        time.sleep(.01)

    nodeCMD = os.path.join(basedir, "dist", "bin", "node")
    daemonCMD =  os.path.join(basedir, "dist", "lib", "daemon.js")
    send_message(encode_message(' starting node processing'))
    nodeP = subprocess.Popen([nodeCMD, daemonCMD], stdout=FNULL, stderr=subprocess.STDOUT)
    send_message(encode_message('finish starting server'))
    send_message(encode_message(str(nodeP)))
    return ipfsP, nodeP


def stopServer(ipfsP, nodeP):
    send_message(encode_message('in stoping server'))
    if os.path.exists(lockFile):
       os.remove(lockFile)
       send_message(encode_message('LockFile removed'))
    nodeP.kill()
    send_message(encode_message('nodeP killed'))
    # This will not kill the ipfs by itself, but this is needed for the sys.exit() to kill it 
    ipfsP.terminate()
    # os.kill(ipfsP.pid, signal.SIGINT)
    send_message(encode_message('ipfsP killed signal sent'))


# functions related to installation
def add_registry_chrome(basedir):
    # TODO: add remove_registry()
    if sys.platform == 'win32':
        keyVal = r'Software\Google\Chrome\NativeMessagingHosts\optract'
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, keyVal, 0, winreg.KEY_ALL_ACCESS)
        except:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, keyVal)
        nativeMessagingMainfest = os.path.join(basedir, 'dist', 'optract-win-chrome.json')
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, nativeMessagingMainfest)
        winreg.CloseKey(key)

        # create optract-win-chrome.json
        with open(nativeMessagingMainfest, 'w') as f:
            manifest_content = create_manifest_chrome('nativeApp.exe', "{extension_id}")
            f.write(manifest_content)
    return


def add_registry_firefox(basedir):
    # TODO: add remove_registry()
    if sys.platform == 'win32':
        keyVal = r'SOFTWARE\Mozilla\NativeMessagingHosts\optract'
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, keyVal, 0, winreg.KEY_ALL_ACCESS)
        except:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, keyVal)
        nativeMessagingMainfest = os.path.join(basedir, 'dist', 'optract-win-firefox.json')
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, nativeMessagingMainfest)
        winreg.CloseKey(key)

        # create optract-win-firefox.json
        with open(nativeMessagingMainfest, 'w') as f:
            manifest_content = create_manifest_firefox('nativeApp.exe')
            f.write(manifest_content)
    return


def createConfig(basedir, dest_file):
    config = {
        "datadir": os.path.join(basedir, "dist", "dapps"),
        "rpcAddr": "https://rinkeby.infura.io/v3/f50fa6bf08fb4918acea4aadabb6f537",
        "defaultGasPrice": "20000000000",
        "gasOracleAPI": "https://ethgasstation.info/json/ethgasAPI.json",
        "condition": "sanity",
        "networkID": 4,
        "passVault": os.path.join(basedir, "dist", "dapps", "myArchive.bcup"),  # this and 'keystore/' are hardcoded in daemon,js
        # "passVault": os.path.join(basedir, "myArchive.bcup"),  # for now, copy into dist/dapps
        "node": {
            "dappdir": os.path.join(basedir, "dist", "dapps"),
            "dns": {
                "server": [
                    "discovery1.datprotocol.com",
                    "discovery2.datprotocol.com"
                ]
            },
            "dht": {
                "bootstrap": [
                    "bootstrap1.datprotocol.com:6881",
                    "bootstrap2.datprotocol.com:6881",
                    "bootstrap3.datprotocol.com:6881",
                    "bootstrap4.datprotocol.com:6881"
                ]
            }
        },
        "dapps": {
            "OptractMedia": {
                "appName": "OptractMedia",
                "artifactDir": os.path.join(basedir, "dist", "dapps", "OptractMedia", "ABI"),
                "conditionDir": os.path.join(basedir, "dist", "dapps", "OptractMedia", "Conditions"),
                "contracts": [
                    { "ctrName": "BlockRegistry", "conditions": ["Sanity"] },
                    { "ctrName": "MemberShip", "conditions": ["Sanity"] }
                ],
                "database": os.path.join(basedir, "dist", "dapps", "OptractMedia", "DB"),
                "version": "1.0",
                "streamr": "false"
            }
        }
    }

    # if previous setting exists, migrate a few settings and make a backup
    if os.path.isfile(dest_file):
        # load previous config
        with open(dest_file, 'r') as f:
            orig = json.load(f)

        try:
            config['dapps']['OptractMedia']['streamr'] = orig['dapps']['OptractMedia']['streamr']
        except KeyError:
            logging.warning('Cannot load "streamr" from previous config file. Use default: "false".')

        # logging.warning('{0} already exists, will overwrite it'.format(dest_file))
        logging.warning('{0} already exists, will move it to {1}'.format(dest_file, dest_file + '.orig'))
        shutil.move(dest_file, dest_file+'.orig')

    # write
    with open(dest_file, 'w') as f:
        json.dump(config, f, indent=4)
        logging.info('config write to file {0}'.format(dest_file))
    return


def extract_node_modules(src, dest):
    # asarBinPath = os.path.join('bin', 'asar')
    # subprocess.check_call([asarBinPath, "extract", "node_modules.asar", "node_modules"], stdout=None, stderr=subprocess.STDOUT)
    dest_node_modules = os.path.join(dest, 'node_modules')
    if os.path.isdir(dest_node_modules):
        shutil.rmtree(dest_node_modules)
    logging.info('extracting latest version of node_modules to ' + dest_node_modules)
    with tarfile.open(src) as tar:
        tar.extractall(dest)
    logging.info('Done extracting latest version of node_modules.')
    return


def prepare_basedir():
    logging.info('Preparing folder for optract in: ' + basedir)

    # generate new empty "dist" directory in basedir
    release_dir = os.path.join(basedir, 'dist')
    release_backup = os.path.join(basedir, 'dist_orig')
    if os.path.isdir(release_dir):
        # keep a backup of previous release
        if os.path.isdir(release_backup):
            shutil.rmtree(release_backup)
        shutil.move(release_dir, release_backup)
    os.mkdir(release_dir)

    # copy files to basedir
    if sys.platform == 'win32':
        nativeApp = os.path.join('nativeApp.exe')
    else:
        nativeApp = os.path.join('nativeApp')
    logging.info('copy {0} to {1}'.format(os.path.join(cwd, 'bin'), os.path.join(release_dir, 'bin')))
    shutil.copytree(os.path.join(cwd, 'bin'), os.path.join(release_dir, 'bin'))
    logging.info('copy {0} to {1}'.format(os.path.join(cwd, 'dapps'), os.path.join(release_dir, 'dapps')))
    shutil.copytree(os.path.join(cwd, 'dapps'), os.path.join(release_dir, 'dapps'))
    logging.info('copy {0} to {1}'.format(os.path.join(cwd, 'lib'), os.path.join(release_dir, 'lib')))
    shutil.copytree(os.path.join(cwd, 'lib'), os.path.join(release_dir, 'lib'))
    logging.info('copy {0} to {1}'.format(nativeApp, release_dir))
    shutil.copy2(nativeApp, release_dir)
    extract_node_modules(os.path.join(cwd, 'node_modules.tar'), release_dir)

    return


def init_ipfs(ipfs_repo):
    ipfs_config = os.path.join(ipfs_repo, 'config')

    if os.path.exists(ipfs_config):
        logging.warning("ipfs repo exists, will use existing one in " + ipfs_repo)
        return

    # create ipfs_repo
    myenv = os.environ.copy()  # "DLL initialize error..." in Windows while set the env inside subprocess calls
    myenv['IPFS_PATH'] = ipfs_repo
    ipfs_bin = os.path.join(basedir, "dist", "bin", "ipfs")

    logging.info("initilalizing ipfs in " + ipfs_repo)
    process = subprocess.Popen([ipfs_bin, "init"], env=myenv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, error = process.communicate()
    logging.info('ipfs results: \n' + str(output))
    if len(error) > 0:
        logging.critical('ipfs error message: \n' + str(error))

    return


def symlink_data(target, name, force=False):
    if os.path.islink(name) and force==True:
        os.remove(name)
    try:
        os.symlink(target, name)
    except:
        logging.warning("Failed to symlink to {0}. Please check manually. Error message:\n{1}".format(target, sys.exc_info()[1]))
    return


def copy_data(src, dest, force=False):
    if os.path.exists(dest) and force==True:
        os.remove(dest)
    if os.path.isdir(src):
        try:
            shutil.copytree(src, dest)
        except:
            logging.warning("Failed to copy directory from {0} to {1}. Please check manually. Error message:\n{2}".format(src, dest, sys.exc_info()[1]))
    else:
        try:
            shutil.copyfile(src, dest)
        except:
            logging.warning("Failed to copy file from {0} to {1}. Please check manually. Error message:\n{2}".format(src, dest, sys.exc_info()[1]))
    return


def sym_or_copy_data(basedir):
    # This function is for developer only. Assume previous config or dir exists.
    # symlink or copy: "ipfs_repo/", "config.json", "keystore", "myArchive.bcup"
    # should deprecate this function after update daemon.js, make daemon.js read data files outside "dist"
    logging.info('Now trying to copy or symlink existing files inside ' + basedir)
    dir_keystore = os.path.join(basedir, 'keystore')
    file_passvault = os.path.join(basedir, 'myArchive.bcup')
    if sys.platform == 'win32':  # In windows, need to run as administrator to symlink(?), so use copy instead
        symcopy = copy_data
    else:
        symcopy = symlink_data
    symcopy(os.path.join(basedir, 'config.json'), os.path.join(basedir, 'dist', 'dapps', 'config.json'), force=True)
    if os.path.isdir(dir_keystore) and os.path.isfile(file_passvault):
        symcopy(dir_keystore, os.path.join(basedir, 'dist', 'dapps', 'keystore'))
        symcopy(file_passvault, os.path.join(basedir, 'dist', 'dapps', 'myArchive.bcup'))
    else:
        os.mkdir(os.path.join(basedir, 'dist', 'dapps', 'keystore'))
    return


def create_manifest_chrome(nativeAppPath, extension_id):
    template = '''
{
  "name": "optract",
  "description": "optract server",
  "path": "{nativeAppPath}",
  "type": "stdio",
  "allowed_origins": [ "chrome-extension://{extension_id}/" ]
}
    '''
    return template.format(nativeAppPath, extension_id)


def create_manifest_firefox(nativeAppPath):
    template = '''
{
  "name": "optract",
  "description": "optract server",
  "path": "{nativeAppPath}",
  "type": "stdio",
  "allowed_extensions": [ "{5b2b58c5-1a22-4893-ac58-9ca33f27cdd4}" ]
}
    '''
    return template.format(nativeAppPath)


def create_and_write_manifest(browser):
    # create manifest file and write to native message folder
    if sys.platform.startswith('win32'):
        if browser == 'chrome':
            add_registry_chrome(basedir)
        elif browser == 'firefox':
            add_registry_firefox(basedir)
    else:  # unix-like
        # determine native message directory for different OS and browsers
        if sys.platform.startswith('linux') and browser == 'chrome':
            nativeMsgDir = os.path.expanduser('~/.config/google-chrome/NativeMessagingHosts')
        elif sys.platform.startswith('linux') and browser == 'firefox':
            nativeMsgDir = os.path.expanduser('~/.mozilla/native-messaging-hosts')
        elif sys.platform.startswith('darwin') and browser == 'chrome':
            nativeMsgDir = os.path.expanduser('~/Library/Application Support/Google/Chrome/NativeMessagingHosts')
        elif sys.platform.startswith('darwin') and browser == 'firefox':
            nativeMsgDir = os.path.expanduser('~/Library/Application Support/Mozilla/NativeMessagingHosts')
        else:
            logging.warning('you should not reach here...')
            raise BaseException('Unsupported platform')

        # create content for manifest file of native messaging
        if browser == 'chrome':
            manifest_content = create_manifest_chrome(nativeAppPath, "extension_id")
        elif browser == 'firefox':
            manifest_content = create_manifest_firefox(nativeAppPath)
        else:
            logging.warning('you should not reach here...')
            raise BaseException('Unsupported browser')

        # write manifest file
        manifest_path = os.path.join(nativeMsgDir, 'optract.json')
        with open(manifest_path, 'w') as f:
            f.write(manifest_content)
    return


# major functions
def install(browser):
    logging.info('Initializing Optract...')
    if not (sys.platform.startswith('linux') or sys.platform.startswith('darwin') or sys.platform.startswith('win32')):
        raise BaseException('Unsupported platform')
    if cwd == basedir:
        raise BaseException('Please do not extract file in the destination directory')
    prepare_basedir()  # copy files to there

    config_file = os.path.join(basedir, 'config.json')
    createConfig(basedir, config_file)

    init_ipfs(ipfs_path)
    sym_or_copy_data(basedir)

    create_and_write_manifest(browser)

    # done
    logging.info('Done! Optract is ready to use.')

    # add a ".installed" to indicate a succesful installation (not used)
    installed = os.path.join(basedir, 'dist', '.installed')
    open(installed, 'a').close()

    return


def main():
    started = False

    logging.info('Start to listen to native message...')
    while True:
        message = get_message()
        if "ping" in message.values() and started == False:
            started = True
            send_message(encode_message('ping->pong'))
            ipfsP, nodeP = startServer()
            logging.info('server started')
            send_message(encode_message('ping->pong more'))
        #if message:
        #    send_message(encode_message("pong")) 
        if "pong" in message.values() and started == True:
            started = False
            send_message(encode_message('pong->ping'))
            stopServer(ipfsP, nodeP)
            send_message(encode_message('pong->ping more'))
            send_message(encode_message('close native app which will also shutdown the ipfs'))
            logging.info('close native app')
            sys.exit(0)
    return


if __name__ == '__main__':
    # startServer()
    if len(sys.argv) > 1:
        if sys.argv[1] == 'install':
            if len(sys.argv) != 2:
                print('Please specify either "firefox" or "chrome"')
                sys.exit(1)
                if (sys.argv[2] != 'firefox' or sys.argv[2] != 'chrome'):
                    print('Only "firefox" or "chrome" are supported at this time.')
                    sys.exit(1)
            print('Installing... please see the progress in logfile: ' + logfile)
            print('Please also download Optract browser extension.')
            install(browser)
        else:
            main()
    else:
        main()
