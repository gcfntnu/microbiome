#! /usr/bin/env python


import sys
import yaml
import os

helptext = '\nUSAGE: make_manifest_qiime2.py /path/to/config.yaml /path/to/manifest.csv\n'

def main(conffile, manifest):
    with open(conffile, 'r') as cfile:
        conf = yaml.load(cfile)
    paired_end = len(conf['read_geometry']) > 1
    fastq_dir = os.path.abspath(conf['fastq_dir'])
    if paired_end:
        header = ['sample-id', 'forward-absolute-filepath', 'reverse-absolute-filepath']
    else:
        header = ['sample-id', 'absolute-filepath']

    with open(manifest, 'w+') as manf:
        manf.write('\t'.join(header) + '\n')

        for s in conf['samples'].keys():
            sample = conf['samples'][s]
            r1_abspath = os.path.join(fastq_dir, sample['R1'])
            if paired_end:
                r2_abspath = os.path.join(fastq_dir, sample['R2'])
                manf.write('{}\t{}\t{}\n'.format(s, r1_abspath, r2_abspath))
            else:
                manf.write('{}\t{}\n'.format(s, r1_abspath))

if __name__ == '__main__':
    try:
        conffile = sys.argv[1]
        manifest = sys.argv[2]
    except:
        print(helptext)
        sys.exit()
        
    main(conffile, manifest)
