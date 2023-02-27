#!/usr/bin/python3

import os, sys, subprocess
import argparse
import platform
import requests
import urllib.request
from os import path
import plistlib
import pathlib
import zipfile
from autodecrypt import scrapkeys, utils
import glob
import shutil
import pyimg4
from pyimg4 import Keybag, Compression
import re
from bs4 import BeautifulSoup

import requests
from pyquery import PyQuery



def run_cmd(cmd):
    subp = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    return subp.stdout.read().decode('utf-8')

# NOTE: This is not my code.
# Had to pluck them out from 'autodecrypt' module and do some very slight modifications on a few of the functions.
# region decrypt_img4 functions


def get_image_type(filename: str):
    """Check if it is IM4P format."""
    if not os.path.isfile(filename):
        print("[e] %s : file not found" % filename)
        sys.exit(-1)
    with open(filename, "rb") as file:
        file.seek(7, 0)
        magic = file.read(4).decode()
        if "M4P" in magic:
            if magic != "IM4P":
                file.seek(-1, os.SEEK_CUR)
            magic = "img4"
        else:
            return None
        file.seek(2, os.SEEK_CUR)
        img_type = file.read(4)
        return magic, img_type


def decrypt_img(infile: str, magic: str, iv: str, key: str) -> int:
    """Decrypt IM4P file. This code is mostly copy/pasta from decrypt_img4.py
       which itself is a copy/pasta from PyIMG4."""
    file = open(infile, 'rb').read()
    im4p = pyimg4.IM4P(file)

    if im4p.payload.encrypted is False:
        print("[i] payload is not encrypted")
        return 0

    if iv is None or key is None:
        print("[e] iv or key is None")
        return -1

    outfile = infile.replace("im4p", "bin")
    print(f"[i] decrypting {infile} to {outfile}...")

    im4p.payload.decrypt(Keybag(key=key, iv=iv))
    # VERY BAD IF STATEMENT HERE WATCH OUT
    # Had to actually do this due to the error "AttributeError: UNKNOWN"
    if Compression(im4p.payload.compression) is not Compression.NONE:
        if Compression(im4p.payload.compression) is not Compression.UNKNOWN:
            print('[i] image4 payload data is compressed, decompressing...')
            im4p.payload.decompress()

    open(outfile, 'wb').write(im4p.payload.output().data)
    print(f"[*] Success Decrypting '{infile}'")
    return 0


# endregion

def run_pcmd(cmd):
    ret = run_cmd(cmd).strip()
    if ret:
        print(ret)


def clean_up():
    print("[*] Cleaning up...")
    files = glob.glob('temp_ramdisk/*')
    for file in files:
        os.remove(file)


def get_gaster(platform):
    base_url = f"https://nightly.link/verygenericname/gaster/workflows/makefile/main/gaster-{platform}.zip"
    print(f"[*] Downloading gaster for platform {platform}...")
    urllib.request.urlretrieve(base_url, f"{platform}/gaster-{platform}.zip")
    if os.path.isfile(f'{platform}/gaster-{platform}.zip'):
        print(f"[*] Downloaded! Extracting...")
        with zipfile.ZipFile(f'{platform}/gaster-{platform}.zip', 'r') as gaster_zip:
            gaster_zip.extractall(platform)
        print(f"[*] Cleaning up...")
        os.remove(f'{platform}/gaster-{platform}.zip')
    else:
        print(f"[!] Failed to download gaster for platform {platform}!")


def get_url_and_build_id(product_type, ios_version):
    ipsw_url = None
    api_path = f'https://api.ipsw.me/v4/device/{product_type}?type=ipsw'
    resp = requests.get(api_path)
    if resp.status_code == 200 and resp.text:
        resp = resp.json()
        for firmware_list in resp['firmwares']:
            if firmware_list['version'] == ios_version:
                ipsw_url = firmware_list['url']
                build_id = firmware_list['buildid']
    return ipsw_url, build_id if ipsw_url is not None and build_id is not None else None


# kerneldiff.py
# https://github.com/verygenericname/SSHRD_Script/blob/main/kerneldiff.py
def kernel_diff(original, patched, bpatchfile):
    print("[*] Comparing patched kernel with original...")
    sizeP = os.path.getsize(patched)
    sizeO = os.path.getsize(original)
    if sizeP != sizeO:
        print("[!] Size does not match, can't compare files!")
    p = open(patched, "rb").read()
    o = open(original, "rb").read()
    diff = []
    for i in range(sizeO):
        originalByte = o[i]
        patchedByte = p[i]
        if originalByte != patchedByte:
            diff.append([hex(i), hex(originalByte), hex(patchedByte)])
    diffFile = open(bpatchfile, 'w+')
    diffFile.write('#AMFI\n\n')
    for d in diff:
        data = str(d[0]) + " " + (str(d[1])) + " " + (str(d[2]))
        diffFile.write(data + '\n')
        print(data)


def download_required_files():
    ipsw_url, build_id = get_url_and_build_id(args.product_type, args.ios)
    if ipsw_url is None or build_id is None:
        print(f'[!] Required files are not found for this version of iOS!')
        exit(1)
    print(f'URL: {ipsw_url}')
    run_pcmd(f"../{sys_platform}/pzb -g BuildManifest.plist {ipsw_url}")
    with open('BuildManifest.plist', 'rb') as build_manifest:
        build_manifest_plist = plistlib.load(build_manifest)
        build_identities = build_manifest_plist['BuildIdentities']
        codename: str = build_identities[0]['Info']['BuildTrain']
        ibss_path: str = build_identities[0]['Manifest']['iBSS']['Info']['Path']
        ibec_path: str = build_identities[0]['Manifest']['iBEC']['Info']['Path']
        devicetree_path: str = build_identities[0]['Manifest']['DeviceTree']['Info']['Path']

        restoreramdisk_path: str = build_identities[0]['Manifest']['RestoreRamDisk']['Info'][
            'Path']
        kernelcache_path: str = build_identities[0]['Manifest']['RestoreKernelCache']['Info'][
            'Path']
        trustcache_path: str = f'Firmware/{restoreramdisk_path}.trustcache'

        run_pcmd(f"../{sys_platform}/pzb -g {ibss_path} {ipsw_url}")
        run_pcmd(f"../{sys_platform}/pzb -g {ibec_path} {ipsw_url}")
        run_pcmd(f"../{sys_platform}/pzb -g {devicetree_path} {ipsw_url}")

        run_pcmd(f"../{sys_platform}/pzb -g {trustcache_path} {ipsw_url}")
        run_pcmd(f"../{sys_platform}/pzb -g {kernelcache_path} {ipsw_url}")
        run_pcmd(f"../{sys_platform}/pzb -g {restoreramdisk_path} {ipsw_url}")

        ibss_path = ibss_path.replace("Firmware/dfu/", "").replace("Firmware/all_flash/", "")
        ibec_path = ibec_path.replace("Firmware/dfu/", "").replace("Firmware/all_flash/", "")
        devicetree_path = devicetree_path.replace("Firmware/dfu/", "").replace("Firmware/all_flash/", "")
        trustcache_path = trustcache_path.replace("Firmware/", "")

        return ibss_path, ibec_path, kernelcache_path, restoreramdisk_path, trustcache_path, devicetree_path, build_id


def get_fw_keys_page(device: str, build: str) -> str:
    """Return the URL of theiphonewiki to parse."""
    wiki = "https://www.theiphonewiki.com"
    data = {"search": build + " " + device}
    response = requests.get(wiki + "/w/index.php", params=data)
    html = response.text
    link = re.search(r"\/wiki\/.*_" + build + r"_\(" + device + r"\)", html)
    if link is not None:
        pagelink = wiki + link.group()
    else:
        pagelink = None
    return pagelink

def getkeys(device: str, build: str):
    pagelink = get_fw_keys_page(device, build)
    print("Page Link: ", pagelink)
    if pagelink is None:
        return None

    html = requests.get(pagelink).content

    soup = BeautifulSoup(html, 'html.parser')
    return_val = \
        {
            "ibss_iv": soup.find("code", id='keypage-ibss-iv').text,
            "ibss_key": soup.find("code", id='keypage-ibss-key').text,
            "ibec_iv": soup.find("code", id='keypage-ibec-iv').text,
            "ibec_key": soup.find("code", id='keypage-ibec-key').text,
        }
    if soup.find("code", id='keypage-ibec2-iv') and soup.find("code", id='keypage-ibec2-key') is not None:
        return_val['ibec2_iv'] = soup.find("code", id='keypage-ibec2-iv').text
        return_val['ibec2_key'] = soup.find("code", id='keypage-ibec2-key').text
    return return_val

# Wrapper around decrypt_img
def decrypt_img4p(infile:str, buildid, iv, key):
    to_decrypt = infile.split('.')[0].lower()

    print(f'[*] Decrypting: "{infile}"...')
    magic = get_image_type(infile)
    print(f'[*] IV: "{iv}"')
    print(f'[*] Key: "{key}"')
    print(f'[*] Magic: "{magic}"')
    return True if decrypt_img(infile, magic, iv, key) == 0 else False



def decrypt_boot_stages(ibss_path, ibec_path, build_id):
    print(f"Decryption mode: {'Gaster' if args.decrypt_mode == 1 else 'Online key fetch'}")

    if args.decrypt_mode == 1:
        run_pcmd(f'../{sys_platform}/gaster pwn')
        run_pcmd(f'../{sys_platform}/gaster reset')
        run_pcmd(f'../{sys_platform}/gaster decrypt {ibss_path} iBSS.dec')
        run_pcmd(f'../{sys_platform}/gaster decrypt {ibec_path} iBEC.dec')
    else:
        keys = getkeys(args.product_type, build_id)
        print(f'[*] Build ID: {build_id}')
        print(f'[*] Product Type: {args.product_type}')
        print("[*] Reached iBSS & iBEC decryption stage!")
        # run_pcmd(f'../{sys_platform}/img4 -i {ibss_path} -o iBSS.dec -k {keys["ibss_iv"]}{keys["ibss_key"]}')
        run_pcmd(f'../{sys_platform}/img4 -i {ibec_path} -o iBEC.dec -k {keys["ibec_iv"]}{keys["ibec_key"]}')
        if not decrypt_img4p(ibss_path, build_id, keys['ibss_iv'].replace('"', ''), keys['ibss_key'].replace('"', '')):
            print('[!] Failed to decrypt iBSS! Aborting...')
            exit(1)
        if not decrypt_img4p(ibec_path, build_id, keys['ibec_iv'].replace('"', ''), keys['ibec_key'].replace('"', '')):
            print('[!] Failed to decrypt iBEC! Aborting...')
            exit(1)


def patch_files(kernelcache_path, devicetree_path, ramdisk_path,
                trustcache_path):
    run_pcmd(f'../{sys_platform}/iBoot64Patcher iBSS.dec iBSS.patched')
    run_pcmd(f'../{sys_platform}/img4 -i iBSS.patched -o ../final_ramdisk/{args.ios}/{args.product_type}/{args.model}/ibss.img4 -M IM4M -A -T ibss')
    if args.boot_args:
        boot_args = args.boot_args
    else:
        boot_args = '"rd=md0 debug=0x2014e -v wdt=-1"'
    if args.cpid == "0x8960" or args.cpid == "0x7000" or args.cpid == "0x7001":
        boot_args = boot_args[:-1]
        boot_args += ' -restore"'
    print(f"[*] Boot arguments: {boot_args}")
    run_pcmd(f'../{sys_platform}/iBoot64Patcher iBEC.dec iBEC.patched -b {boot_args} -n')
    run_pcmd(f'../{sys_platform}/img4 -i iBEC.patched -o ../final_ramdisk/{args.ios}/{args.product_type}/{args.model}/iBEC.img4 -M IM4M -A -T ibec')
    run_pcmd(f'../{sys_platform}/img4 -i {kernelcache_path} -o kcache.raw')
    run_pcmd(f'../{sys_platform}/Kernel64Patcher kcache.raw kcache.patched -a')
    kernel_diff('kcache.raw', 'kcache.patched', 'kcache.bpatch')
    is_linux = '-J' if sys_platform == 'Linux' else ''
    run_pcmd(
        f'../{sys_platform}/img4 -i {kernelcache_path} -o ../final_ramdisk/{args.ios}/{args.product_type}/{args.model}/kernelcache.img4 -M IM4M -T rkrn -P kcache.bpatch {is_linux}')
    run_pcmd(
        f'../{sys_platform}/img4 -i {devicetree_path} -o ../final_ramdisk/{args.ios}/{args.product_type}/{args.model}/devicetree.img4 -M IM4M -T rdtr')

    run_pcmd(
        f'../{sys_platform}/img4 -i {trustcache_path} -o ../final_ramdisk/{args.ios}/{args.product_type}/{args.model}/trustcache.img4 -M IM4M -T rtsc')
    run_pcmd(f'../{sys_platform}/img4 -i {ramdisk_path} -o ramdisk.dmg')
    patch_ramdisk()
    run_pcmd(
        f'../{sys_platform}/img4 -i ../other/logo.im4p -o ../final_ramdisk/{args.ios}/{args.product_type}/{args.model}/logo.img4 -A -T rlgo -M IM4M')


def patch_ramdisk():
    print("[*] Patching ramdisk...")
    if sys_platform == 'Darwin':
        run_pcmd('hdiutil resize -size 210MB ramdisk.dmg')
        run_pcmd('hdiutil attach -mountpoint /tmp/SSHRD ramdisk.dmg')

        if args.model == 'j42dap':
            run_pcmd(f'../{sys_platform}/gtar -x --no-overwrite-dir -f ../sshtars/atvssh.tar.gz -C /tmp/SSHRD/')
        elif args.cpid == '0x8012':
            run_pcmd(f'../{sys_platform}/gtar -x --no-overwrite-dir -f ../sshtars/t2ssh.tar.gz -C /tmp/SSHRD/')
            print("[!] !!! T2 SSH might hang and do nothing when booting !!!")
        else:
            run_pcmd(f'../{sys_platform}/gtar -x --no-overwrite-dir -f ../sshtars/ssh.tar.gz -C /tmp/SSHRD/')

        run_pcmd('hdiutil detach -force /tmp/SSHRD')
        run_pcmd('hdiutil resize -sectors min ramdisk.dmg')
    else:
        run_pcmd(f'../{sys_platform}/hfsplus ramdisk.dmg grow 210000000 > /dev/null')

        if args.model == 'j42dap':
            run_pcmd(f'../{sys_platform}/hfsplus ramdisk.dmg untar ../sshtars/atvssh.tar > /dev/null')
        elif args.cpid == '0x8012':
            run_pcmd(f'../{sys_platform}/hfsplus ramdisk.dmg untar ../sshtars/t2ssh.tar > /dev/null')
            print("[!] !!! T2 SSH might hang and do nothing when booting !!!")
        else:
            run_pcmd(f'../{sys_platform}/hfsplus ramdisk.dmg untar ../sshtars/ssh.tar > /dev/null')
    run_pcmd(
        f'../{sys_platform}/img4 -i ramdisk.dmg -o ../final_ramdisk/{args.ios}/{args.product_type}/{args.model}/ramdisk.img4 -M IM4M -A -T rdsk')


if __name__ == '__main__':
    main_root_dir = os.path.realpath(os.path.dirname(__file__))
    sys_platform = platform.uname().system
    print(f"[*] System platform: {sys_platform}")
    if sys_platform == 'Windows':
        print("[*] This tool is not supported on Windows, it needs Linux or MacOS.")
        exit(1)
    os.system('clear')
    parser = argparse.ArgumentParser(description='SSH Ramdisk creation tool.')
    parser.add_argument('--decrypt_mode', '-d', type=int,
                        help="'0' is decryption using keys fetched online, '1' is decryption with Gaster",
                        required=True)
    parser.add_argument('--cpid', '-c', type=str, help='CPID of device (example 0x8000)', required=True)
    parser.add_argument('--model', '-m', type=str, help='Model of device (example n71ap)', required=True)
    parser.add_argument('--product_type', '-pt', type=str, help='Product type of device (example iPhone8,1)',
                        required=True)
    parser.add_argument('--ios', '-i', type=str, help='iOS version for the ramdisk (example 15.7)', required=True)
    parser.add_argument('--boot_args', '-ba', type=str,
                        help='iOS arguments to execute during boot. Default: "rd=md0 debug=0x2014e -v wdt=-1"')
    args = parser.parse_args()
    # People might mistakenly use commas in the iOS version.
    if args.ios is not None and ',' in args.ios:
        args.ios = args.ios.replace(',', '.')
    if args.ios is not None and not float(args.ios) >= 15:
        print("[!] iOS version can't be below 15. Exitting...")
        exit(1)
    if not path.isfile(f'other/shsh/{args.cpid}.shsh'):
        print(f'[!] CPID ({args.cpid}) is not found or is not supported.')
        exit(1)

    if not os.path.isfile(f'{sys_platform}/gaster') and args.decrypt_mode == 1:
        print("[!] gaster does not appear to exist! Downloading a new one...\n")
        get_gaster(sys_platform)

    pathlib.Path('temp_ramdisk').mkdir(exist_ok=True, parents=True)
    pathlib.Path('final_ramdisk').mkdir(exist_ok=True, parents=True)
    pathlib.Path(f'final_ramdisk/{args.ios}/{args.product_type}').mkdir(exist_ok=True, parents=True)

    if path.isdir(f'final_ramdisk/{args.ios}/{args.product_type}/{args.model}'):
        choice = input(f'[!] Data for {args.product_type} ({args.model}/{args.ios}) already exists! Do you want to delete them and start over? (y/N): ') or 'N'
        if choice.lower() == 'n':
            print('[*] Exiting...')
            exit(0)
        shutil.rmtree(f'final_ramdisk/{args.ios}/{args.product_type}/{args.model}')
    # files = glob.glob('temp_ramdisk/*')
    # for file in files:
    #     os.remove(file)

    pathlib.Path(f'final_ramdisk/{args.ios}/{args.product_type}/{args.model}').mkdir(exist_ok=True, parents=True)

    os.chdir('temp_ramdisk')
    run_pcmd(f"../{sys_platform}/img4tool -e -s ../other/shsh/{args.cpid}.shsh -m IM4M")

    ibss_path, ibec_path, kernelcache_path, restoreramdisk_path, trustcache_path, devicetree_path, build_id = download_required_files()
    decrypt_boot_stages(ibss_path, ibec_path, build_id)
    patch_files(kernelcache_path, devicetree_path, restoreramdisk_path, trustcache_path)

    os.chdir('../')
    # clean_up()
    print(f"[*] Ramdisk files saved to: {main_root_dir}/final_ramdisk/{args.ios}/{args.product_type}/{args.model}")
    print("[*] Done!")
    print("Python version was made by Bonkeyzz.")
    print("Original Shell script was made by verygenericname (https://github.com/verygenericname).")
