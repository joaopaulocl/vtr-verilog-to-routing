#!/usr/bin/python
__version__ = """$Revison$
                 Last Change: $Author$ $Date$
                 Orig Author: kmurray
                 $Id: vqm2blif_flow.py 2664 2012-06-21 22:20:09Z kmurray $"""

#try:
#    import pudb
#except ImportError:
#    pass

import sys
import argparse
import subprocess
import os
from os import path

def parse_args():
    description="""\
    Runs the VQM2BLIF flow on the specified Quartus 2 Project to generate a BLIF file,
    and optionally run VPR on that file.

    The quartus project is compiled in its directory, and by default the
    vqm and blif files are generated in the directory where the script is called.
    """

    parser = argparse.ArgumentParser(usage="%(prog)s [-h] -q QUARTUS_PROJECT [--vpr] [other options]",
                                    description=description)

    parser.add_argument('--version', action='version', version=__version__,
                        help='Version information')

    #Options effecting quartus operation
    quartus_options = parser.add_argument_group('quartus options')

    quartus_options.add_argument('-q', '--quartus_project', dest='quartus_project', action='store',
                        required=True,
                        help='The Quartus 2 project file of the design to be used')

    quartus_options.add_argument('-f', '--family', dest='device_family', action='store',
                        default='stratixiv',
                        help='The device family to target (default: %(default)s)')

    quartus_options.add_argument('--no_resynth', dest='do_resynthesis', action='store_false',
                        default=True,
                        help='If the vqm output file already exists, do not re-run Quartus 2 to re-synthesize it')


    #Options effecting vqm2blif operation
    vqm2blif_options = parser.add_argument_group('vqm2blif options')

    vqm2blif_options.add_argument('-b', '--blif', dest='blif_file', action='store',
                        help='The output blif file name (default: <project>_<family>.blif')

    vqm2blif_options.add_argument('-v', '--vqm', dest='vqm_file', action='store',
                        help='The output vqm file name (default: <project>_<family>.vqm)')

    vqm2blif_options.add_argument('-a', '--arch', dest='arch_file', action='store',
                        help='The architecture file to use (default: $V2B_REGRESSION_BASE_DIR/BENCHMARKS/ARCH/<project>_arch.xml)')

    vqm2blif_options.add_argument('--vqm2blif_opts', dest='vqm2blif_extra_opts', action='store',
                        default='-luts vqm', #Outputs blackbox primitives only (no blif .names)
                        help='Provide additional options to vqm2blif as a string (default: "%(default)s")')


    #Options effecting vpr operation
    vpr_options = parser.add_argument_group('vpr options')

    vpr_options.add_argument('--vpr', dest='run_vpr', action='store_true',
                            default=False,
                            help='Run vpr on the generated blif file (default: %(default)s)')

    vpr_options.add_argument('--vpr_opts', dest='vpr_opts', action='store',
                            default="--fast --timing_analysis off -route_chan_width 300 --nodisp",
                            help='Provide additional options to vpr as a string (default: "%(default)s")')


    #External tool location overrides
    exec_options = parser.add_argument_group('external tool override options')
    
    exec_options.add_argument('--vqm2blif_dir', dest='vqm2blif_dir', action='store',
                              help='Override the default vqm2blif directory (default: V2B_REGRESSION_BASE_DIR environment variable)')

    exec_options.add_argument('--quartus_dir', dest='quartus_dir', action='store',
                              help='Override the default quartus binary directory (default: QII_BASE_DIR environment variable)')

    exec_options.add_argument('--vpr_dir', dest='vpr_dir', action='store',
                              help='Override the default vpr directory (default: VPR_BASE_DIR environment variable)')


    args = parser.parse_args()

    return args

def check_args(args):
    """
        Verifies arguments and sets some defaults that can not be easily computed
        in the main argument parser
    """
    #Query environment for base directories if not specified
    if not args.vqm2blif_dir:
        try:
            args.vqm2blif_dir = os.environ['V2B_REGRESSION_BASE_DIR']
        except KeyError:
            raise ValueError, "could not find vqm2blif directory based on V2B_REGRESSION_BASE_DIR environment variable or command line option"

    if not args.quartus_dir:
        try:
            args.quartus_dir = os.environ['QII_BASE_DIR']
        except KeyError:
            raise ValueError, "could not find vqm2blif directory based on QII_BASE_DIR environment variable or command line option" 

    #Only if we are trying to run VPR do we need to find the executable
    if args.run_vpr and not args.vpr_dir:
        try:
            args.vpr_dir = os.environ['VPR_BASE_DIR']
        except KeyError:
            raise ValueError, "could not find vpr directory based on VPR_BASE_DIR environment variable or command line option"

    #Generate default filenames if not specified
    if not args.vqm_file:
        args.vqm_file = path.splitext(path.basename(args.quartus_project))[0] + '_' + args.device_family + '.vqm'

    if not args.blif_file:
        args.blif_file = path.splitext(path.basename(args.quartus_project))[0] + '_' + args.device_family + '.blif'

    if not args.arch_file:
        args.arch_file = path.join(args.vqm2blif_dir, 'BENCHMARKS/ARCH/%s_arch.xml' % args.device_family)
    
    return args


def gen_vqm(args):
    """
    Generates a vqm file from a quartus project
    using quartus_sh
    """
    #Save the current directory, since we will return here
    script_run_dir = os.getcwd()

    #Must run quartus from the directory containing the project file
    quartus_project_file = path.basename(args.quartus_project)
    quartus_project_dir = path.dirname(args.quartus_project)

    #Absolute path to vqm file, so it ends up in the script run directory
    args.vqm_file = path.join(os.getcwd(), args.vqm_file)

    #Re-synthesize if told so, or if the file doesn't exist
    if args.do_resynthesis or not path.isfile(args.vqm_file):

        if quartus_project_dir != '':
            #Project directory is not the current directory, so move
            print "INFO: moving to quartus project directory '%s'" % (quartus_project_dir)
            os.chdir(quartus_project_dir)

        #Quartus Verilog to VQM conversion script
        q2_write_vqm_tcl = path.join(args.vqm2blif_dir, 'SCRIPTS/q2_write_vqm.tcl')

        q2_shell = path.join(args.quartus_dir, 'quartus_sh')
        q2_cmd = [q2_shell,
                    '--64bit',
                    '-t',               q2_write_vqm_tcl,
                    '-project',         quartus_project_file,
                    '-family',          args.device_family,
                    '-cdb_merge',       
                    '-vqm_out_file',    args.vqm_file]

        #Verilog to vqm conversion
        try:
            print "\nINFO: Calling Quartus"
            print_cmd(q2_cmd)
            subprocess.check_call(q2_cmd)
        except subprocess.CalledProcessError as error:
            print "ERROR: VQM generation failed (retcode: %s)" % error.returncode
            sys.exit(1)

        #Move back to script run dir
        print "INFO: moving back to script run directory '%s'" % (script_run_dir)
        os.chdir(script_run_dir)

    else:
        print "INFO: found existing VQM file, not re-synthesizing"
    

def gen_blif(args):
    """
    Converts a vqm file to a blif file
    using vqm2blif.exe
    """
    #VQM to blif conversion
    vqm2blif_exec = path.join(args.vqm2blif_dir, '../vqm2blif.exe')

    vqm2blif_cmd = [vqm2blif_exec,
                    '-arch',            args.arch_file,
                    '-vqm',             args.vqm_file,
                    '-out',             args.blif_file]

    #Add any extra command line options
    if args.vqm2blif_extra_opts:
        vqm2blif_cmd = vqm2blif_cmd + args.vqm2blif_extra_opts.split()
    
    try:
        print "\nINFO: Calling vqm2blif"
        print_cmd(vqm2blif_cmd)
        subprocess.check_call(vqm2blif_cmd)
    except subprocess.CalledProcessError as error:
        print "ERROR: VQM2BLIF conversion failed (retcode: %s)" % error.returncode
        sys.exit(1)



def run_vpr(args):
    """
    Runs vpr on the generated blif file
    """
    vpr_exec = path.join(args.vpr_dir, 'vpr')

    vpr_cmd = [vpr_exec,
               args.arch_file,
               path.splitext(args.blif_file)[0]]
    
    if args.vpr_opts:
        vpr_cmd = vpr_cmd + args.vpr_opts.split()

    try:
        print "\nINFO: Calling VPR"
        print_cmd(vpr_cmd)
        subprocess.check_call(vpr_cmd)
    except subprocess.CalledProcessError as error:
        print "ERROR: VPR run failed (retcode: %s)" % error.returncode
        sys.exit(1)
    print "\nINFO: VPR ran successfully"

def print_cmd(cmd_array):
    print ' '.join(cmd_array)

def vqm2blif_flow(args):
    gen_vqm(args)

    gen_blif(args)

if __name__ == '__main__':
    args = parse_args()
    
    args = check_args(args)

    vqm2blif_flow(args) 
    
    if args.run_vpr:
        run_vpr(args)

    print "\nINFO: script complete"
