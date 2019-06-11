#! /usr/bin/env python

import sys
import getopt
import yaml

def main(argv):
	configfile = ''
	outputfile = ''
	try:
		opts, args = getopt.getopt(argv,"hc:o:",["config=","ofile=",])
	except getopt.GetoptError:
		print('Error')
		print('create_qiime_map.py -c <config-file> -o <output-fna>')
		sys.exit(2)
	for opt, arg in opts:
		if opt == '-h':
			print('create_qiime_map.py -c <config-file> -o <output-fna>')
			sys.exit()
		elif opt in ("-c", "--config-file"):
			configfile = arg
		elif opt in ("-o", "--ofile"):
			outputfile = arg
	cfile = open(configfile,'r')
	ofile = open(outputfile, 'w+')
	ofile.write('#SampleID\tBarcodeSequence\tLinkerPrimerSequence\tFileInput\n')
	config = yaml.load(cfile)
	sample_ids = config['samples'].keys()
	for sid in sample_ids:
		ofile.write('{}\t\t\t{}.assembled_filtered.nonchimera.fasta\n'.format(sid,sid))
	cfile.close()
	ofile.close()
	
if __name__ == "__main__":
	main(sys.argv[1:])


