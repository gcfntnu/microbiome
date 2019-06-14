#!/usr/bin/env Rscript
args = commandArgs(trailingOnly=TRUE)

suppressWarnings(library(phyloseq))

biom.fn <- args[1]
tree.fn <- args[2]
out.fn <- args[3]

PS <- import_biom(biom.fn, tree.fn)
TAX <- tax_table(PS)
tax.names <- c("Kingdom","Phylum","Class","Order","Family","Genus","Species")[1:length(colnames(TAX))]
colnames(tax_table(PS)) <- tax.names

## filter taxa
##OTU <- otu_table(PS)
##n.min <- 3
##n.samples.min <- ncol(OTU) - 1
##out <- (rowSums(OTU <= n.min) >= n.samples.min) & (rowSums(OTU) <= (2*n.min))
##OTU <- OTU[out==FALSE,]
##otu_table(PS) <- OTU

## type convert sample data
sample_data(PS)[] <- lapply(sample_data(PS), function(x) type.convert(as.character(x), as.is = TRUE))

saveRDS(PS, out.fn)
