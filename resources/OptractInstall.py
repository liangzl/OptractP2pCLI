#!/usr/bin/env python
from __future__ import print_function
import os
import sys
import shutil
import tarfile
import json
import subprocess
import hashlib
import logging
log = logging.getLogger(__name__)

if sys.platform == "win32":
    import winreg


class OptractInstall():
    def __init__(self, basedir, distdir, datadir):
        if not (sys.platform.startswith('linux') or sys.platform.startswith('darwin') or sys.platform.startswith('win32')):
            raise BaseException('Unsupported platform')
        self.basedir = basedir
        self.distdir = distdir
        self.datadir = datadir
        self.installed = os.path.join(self.distdir, '.installed')
        extid_file = os.path.join(self.distdir, 'extension_id.json')  # or write fix values here?
        try:
            with open(extid_file, 'r') as f:
                self.extid = json.load(f)
        except IOError:  # python3: FileNotFoundError
            logging.error('Failed to find file: {0}'.format(extid_file))
            sys.exit(1)

        self.message = 'Welcome to Optract'  # message to systray or other modules

    def install(self, force=False):
        if (not os.path.isdir(self.distdir)) or (not os.path.isdir(self.basedir)):
            # TODO: cannot see this raise... maybe return something to systray then systray popup warning then exit?
            raise BaseException('Cannot find folder \'{0}\' or \'{1}\' (forget to extract zip first?)'.format(self.distdir, self.basedir))
            sys.exit(1)
        if not os.path.isfile(self.installed) or force:
            logging.info('Initializing Optract in {0}'.format(self.distdir))
            self.prepare_files()
            self.create_config()
            self.init_ipfs()
            # install for all supporting browsers (for now assume firefox is must)
            if not self.create_and_write_manifest('firefox'):
                logging.warning('Failed to create manifest for firefox')
            if not self.create_and_write_manifest('chrome'):
                logging.warning('Failed to create manifest for chrome')
            logging.info('Done! Optract is ready to use.')
            self.message = 'Done! Optract is ready to use.'
            open(self.installed, 'a').close()
        else:
            logging.warning('Already installed in {0}'.format(self.distdir))

    def add_registry_chrome(self):
        # TODO: add remove_registry()
        if sys.platform == 'win32':
            keyVal = r'Software\Google\Chrome\NativeMessagingHosts\optract'
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, keyVal, 0, winreg.KEY_ALL_ACCESS)
            except WindowsError:  # WindowsError for python2; OSError in python3
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, keyVal)
            nativeMessagingMainfest = os.path.join(self.distdir, 'optract-win-chrome.json')
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, nativeMessagingMainfest)
            winreg.CloseKey(key)

            # create optract-win-chrome.json
            with open(nativeMessagingMainfest, 'w') as f:
                manifest_content = self.create_manifest_chrome('nativeApp\\nativeApp.exe', self.extid['chrome'])
                json.dump(manifest_content, f, indent=4)
        return

    def add_registry_firefox(self):
        # TODO: add remove_registry()
        if sys.platform == 'win32':
            keyVal = r'SOFTWARE\Mozilla\NativeMessagingHosts\optract'
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, keyVal, 0, winreg.KEY_ALL_ACCESS)
            except WindowsError:  # WindowsError for python2; OSError in python3
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, keyVal)
            nativeMessagingMainfest = os.path.join(self.distdir, 'optract-win-firefox.json')
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, nativeMessagingMainfest)
            winreg.CloseKey(key)

            # create optract-win-firefox.json
            with open(nativeMessagingMainfest, 'w') as f:
                manifest_content = self.create_manifest_firefox('nativeApp\\nativeApp.exe', self.extid['firefox'])
                json.dump(manifest_content, f, indent=4)
        return

    def init_ipfs(self):
        ipfs_path = os.path.join(self.datadir, 'ipfs_repo')
        ipfs_config = os.path.join(ipfs_path, 'config')

        if os.path.exists(ipfs_config):
            logging.warning("ipfs repo exists, will use existing one in " + ipfs_path)
            self.message = "ipfs repo exists, will use existing one in " + ipfs_path
            return

        # create ipfs_repo
        myenv = os.environ.copy()  # "DLL initialize error..." in Windows while set the env inside subprocess calls
        myenv['IPFS_PATH'] = ipfs_path
        ipfs_bin = os.path.join(self.distdir, "bin", "ipfs")

        logging.info("initilalizing ipfs in " + ipfs_path)
        self.message = "initilalizing ipfs in " + ipfs_path
        process = subprocess.Popen([ipfs_bin, "init"], env=myenv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        logging.info('ipfs results: \n' + str(output))
        if len(error) > 0:
            logging.critical('ipfs error message: \n' + str(error))
        return

    def create_manifest_chrome(self, nativeAppPath, extension_id):
        # extension_id = "jlanclpnebjipbolljoenepmcofibpmk"
        manifest_json = {
            "name": "optract",
            "description": "optract server",
            "path": nativeAppPath,
            "type": "stdio",
            "allowed_origins": ["chrome-extension://{0}/".format(extension_id)]
        }
        return manifest_json

    def create_manifest_firefox(self, nativeAppPath, extension_id):
        # extension_id = "{5b2b58c5-1a22-4893-ac58-9ca33f27cdd4}"
        manifest_json = {
            "name": "optract",
            "description": "optract server",
            "path": nativeAppPath,
            "type": "stdio",
            "allowed_extensions": [extension_id]
        }
        return manifest_json

    def get_manifest_path(self, browser):
        if sys.platform.startswith('win32'):
            extension_manifest = os.path.join(self.distdir, 'optract-win-{0}.json'.format(browser))
        elif sys.platform.startswith('linux') and browser == 'chrome':
            extension_manifest = os.path.expanduser('~/.config/google-chrome/NativeMessagingHosts/optract.json')
        elif sys.platform.startswith('linux') and browser == 'firefox':
            extension_manifest = os.path.expanduser('~/.mozilla/native-messaging-hosts/optract.json')
        elif sys.platform.startswith('darwin') and browser == 'chrome':
            extension_manifest = os.path.expanduser('~/Library/Application Support/Google/Chrome/NativeMessagingHosts/optract.json')
        elif sys.platform.startswith('darwin') and browser == 'firefox':
            extension_manifest = os.path.expanduser('~/Library/Application Support/Mozilla/NativeMessagingHosts/optract.json')
        else:
            # raise BaseException('Unsupported platform and/or browser.')
            logging.error('Unsupported platform and/or browser.')
            extension_manifest = None
        return extension_manifest

    def check_manifest_path(self, browser):
        if sys.platform.startswith('win32'):
            # TODO: check registry
            content = None  # add something later
        else:
            manifest_path = self.get_manifest_path(browser)
            if os.path.isfile(manifest_path):
                # try...except open?
                with open(manifest_path, 'r') as f:
                    content = f.load(f)
            else:
                content = None
        return content

    def create_and_write_manifest(self, browser):
        # logging.info('in creating manifest...')
        if browser not in ['firefox', 'chrome']:
            raise BaseException('Unsupported browser {0}'.format(browser))

        # create manifest file and write to native message folder
        if sys.platform.startswith('win32'):
            if browser == 'chrome':
                self.add_registry_chrome()
            elif browser == 'firefox':
                self.add_registry_firefox()
        else:  # unix-like
            manifest_path = self.get_manifest_path(browser)

            # mkdir for browser nativeMessageingHost (is it necessary?)
            browser_nativeMsg_dir = os.path.dirname(manifest_path)
            if not os.path.isdir(browser_nativeMsg_dir):
                try:
                    os.mkdir(browser_nativeMsg_dir)
                except OSError:  # most likely due to parent dir of browser_nativeMsg_dir not exist
                    logging.error('Failed to create folder {0} for {1} browser.'.format(browser_nativeMsg_dir, browser))
                    return False

            # create content for manifest file of native messaging
            nativeAppPath = os.path.join(self.distdir, 'nativeApp', 'nativeApp')
            if browser == 'chrome':
                manifest_content = self.create_manifest_chrome(nativeAppPath, self.extid[browser])
            elif browser == 'firefox':
                manifest_content = self.create_manifest_firefox(nativeAppPath, self.extid[browser])

            # write manifest file (overwrite existing one)
            logging.info('create manifest in {0}'.format(manifest_path))
            with open(manifest_path, 'w') as f:
                json.dump(manifest_content, f, indent=4)
        return True

    def _compare_md5(self, filename, md5_expected):
        md5_seen = hashlib.md5(open(filename, 'rb').read()).hexdigest()
        if md5_seen != md5_expected:
            raise BaseException('The md5sum of file {0} is inconsistent with expected hash.'.format(filename))

    def check_md5(self):
        if sys.platform.startswith('win32'):
            node_md5_expected = 'f293ba8c28494ecd38416aa37443aa0d'
            ipfs_md5_expected = 'bbed13baf0da782311a97077d8990f27'
            node_modules_tar_md5_expected = 'f177837cd1f3b419279b52a07ead78ce'
        elif sys.platform.startswith('linux'):
            node_md5_expected = '8a9aa6414470a6c9586689a196ff21e3'
            ipfs_md5_expected = 'ee571b0fcad98688ecdbf8bdf8d353a5'
            node_modules_tar_md5_expected = '745372d74f1be243764268ac84b4ab8d'
        elif sys.platform.startswith('darwin'):
            node_md5_expected = 'b4ba1b40b227378a159212911fc16024'
            ipfs_md5_expected = '5e8321327691d6db14f97392e749223c'
            node_modules_tar_md5_expected = '6f997ad2bac5f0fa3db05937554c9223'

        if sys.platform.startswith('win32'):
            nodeCMD = os.path.join(self.distdir, 'bin', 'node.exe')
            ipfsCMD = os.path.join(self.distdir, 'bin', 'ipfs.exe')
        else:
            nodeCMD = os.path.join(self.distdir, 'bin', 'node')
            ipfsCMD = os.path.join(self.distdir, 'bin', 'ipfs')
        node_modules_tar = os.path.join(self.distdir, 'node_modules.tar')
        self._compare_md5(nodeCMD, node_md5_expected)
        self._compare_md5(ipfsCMD, ipfs_md5_expected)
        self._compare_md5(node_modules_tar, node_modules_tar_md5_expected)
        return

    def prepare_files(self):
        logging.info('Preparing folder for optract in: ' + self.basedir)

        # check md5sum
        self.check_md5()

        self.extract_node_modules(os.path.join(self.distdir, 'node_modules.tar'), self.distdir)

        logging.info('creating keystore folder if necessary')
        self.message = 'creating keystore folder if necessary'
        key_folder = os.path.join(self.datadir, 'keystore')
        if not os.path.isdir(key_folder):
            os.mkdir(key_folder)
        return

    def create_config(self):
        config = {
            "datadir": self.datadir,  # while update, replace the "dist/" folder under basedir
            "rpcAddr": "https://rinkeby.infura.io/v3/f50fa6bf08fb4918acea4aadabb6f537",
            "defaultGasPrice": "20000000000",
            "gasOracleAPI": "https://ethgasstation.info/json/ethgasAPI.json",
            "condition": "sanity",
            "networkID": 4,
            "passVault": os.path.join(self.datadir, "myArchive.bcup"),
            "node": {
                "dappdir": os.path.join(self.distdir, "dapps"),
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
                    "artifactDir": os.path.join(self.distdir, "dapps", "OptractMedia", "ABI"),
                    "conditionDir": os.path.join(self.distdir, "dapps", "OptractMedia", "Conditions"),
                    "contracts": [
                        {"ctrName": "BlockRegistry", "conditions": ["Sanity"]},
                        {"ctrName": "MemberShip", "conditions": ["Sanity"]}
                    ],
                    "database": os.path.join(self.distdir, "dapps", "OptractMedia", "DB"),
                    "version": "1.0",
                    "streamr": "false"
                }
            }
        }

        # if previous setting exists, migrate a few settings and make a backup
        config_file = os.path.join(self.datadir, 'config.json')
        if os.path.isfile(config_file):
            # load previous config
            with open(config_file, 'r') as f:
                orig = json.load(f)

            try:
                config['dapps']['OptractMedia']['streamr'] = orig['dapps']['OptractMedia']['streamr']
            except KeyError:
                logging.warning('Cannot load "streamr" from previous config file. Use default: "false".')

            logging.warning('{0} already exists, will move it to {1}'.format(config_file, config_file + '.orig'))
            shutil.move(config_file, config_file + '.orig')

        # write
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)
            logging.info('config write to file {0}'.format(config_file))
        return

    def extract_node_modules(self, src, dest):
        # asarBinPath = os.path.join('bin', 'asar')
        # subprocess.check_call([asarBinPath, "extract", "node_modules.asar", "node_modules"], stdout=None, stderr=subprocess.STDOUT)
        dest_node_modules = os.path.join(dest, 'node_modules')
        if os.path.isdir(dest_node_modules):
            shutil.rmtree(dest_node_modules)
        logging.info('extracting latest version of node_modules to ' + dest_node_modules)
        self.message = 'extracting latest version of node_modules to ' + dest_node_modules

        def _track_progress(members):
            nfiles_extracted = 0
            for member in members:
                yield member  # this will be the current file being extracted
                nfiles_extracted += 1
                # print(('{0} \t{0}/{1}'.format(member.name, nfiles_extracted, nfiles)))
                self.message = 'extracting... {0:.2f}% done\nGet firefox/chrome add-ons from 11be.org'.format(100 * nfiles_extracted / float(nfiles))

        with tarfile.open(src) as tar:
            nfiles = len(tar.getnames())
            tar.extractall(path=dest, members=_track_progress(tar))
        logging.info('Done extracting latest version of node_modules.')
        return


def main(basedir, distdir, datadir):
    installer = OptractInstall(basedir, distdir, datadir)
    installer.install()
    return


if __name__ == '__main__':
    # print("please do not run this script directly")
    pass
