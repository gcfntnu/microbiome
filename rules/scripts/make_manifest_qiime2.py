#! /usr/bin/env python


import sys
import yaml
import os

helptext = '\nUSAGE: make_manifest_qiime2.py /path/to/config.yaml /path/to/manifest.csv\n'

def main(conffile, manifest):
    with open(conffile, 'r') as cfile:
        conf = yaml.load(cfile)
    fastq_dir = os.path.abspath(conf['fastq_dir'])
    header = ['sample-id', 'absolute-filepath', 'direction']

    with open(manifest, 'w+') as manf:
        manf.write(','.join(header) + '\n')

        for s in conf['samples'].keys():
            sample = conf['samples'][s]
            for r1 in sample['R1'].split(','):
                r1_abspath = os.path.join(fastq_dir, r1)
                manf.write('{},{},forward\n'.format(s, r1_abspath))
            if not 'R2' in sample:

            for r2 in sample['R2'].split(','):
                    r2_abspath = os.path.join(fastq_dir, r2)
                    manf.write('{},{},reverse\n'.format(s, r2_abspath))

if __name__ == '__main__':
    try:
        conffile = sys.argv[1]
        manifest = sys.argv[2]
    except:
        print(helptext)
        sys.exit()
        
    main(conffile, manifest)
