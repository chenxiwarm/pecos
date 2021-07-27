#!/usr/bin/env python3 -u
#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
#  with the License. A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0/
#
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
#  OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions
#  and limitations under the License.

import argparse
import os

import numpy as np
import scipy.sparse as smat
from pecos.utils import smat_util
from pecos.utils.cli import SubCommand
from pecos.utils.featurization.text.vectorizers import Vectorizer, vectorizer_dict


class Preprocessor(object):
    """Preprocess text to numerical values"""

    def __init__(self, vectorizer=None):
        """Initialization

        Args:
            vectorizer (Vectorizer): Text vectorizer class instance.
        """
        self.vectorizer = vectorizer

    def save(self, preprocessor_folder):
        """Save the preprocess object to a folder

        Args:
            preprocessor_folder (str): The saving folder name
        """
        self.vectorizer.save(preprocessor_folder)

    @classmethod
    def load(cls, preprocessor_folder):
        """Load preprocessor

        Args:
            preprocess_folder (str): The folder to load

        Returns:
            cls: An instance of Preprocessor
        """

        vectorizer = Vectorizer.load(preprocessor_folder)
        return cls(vectorizer)

    @classmethod
    def train(cls, corpus, vectorizer_config, dtype=np.float32):
        """Train a preprocessor

        Args:
            corpus (list of strings or a string): Training text input.
                If given a list of strings, it's the list of training inputs.
                If given a string, it's the path to a file with lines of text inputs to be trained.
            vectorizer_config (dict): Config file for the vectorizer
            dtype (scipy.dtype): Data type for the vectorized output

        Returns:
            A Preprocessor
        """

        vectorizer = Vectorizer.train(corpus, vectorizer_config, dtype=dtype)
        return cls(vectorizer)

    def predict(self, corpus, **kwargs):
        """Vectorize a corpus

        Args:
            corpus (list of strings or a string): Predicting text input.
                If given a list of strings, it's the list of text input to be vectorized.
                If given a string, it's the path to a file with lines of text inputs to be vectorized.
            kwargs (optional): Args to be passed to Vectorizer

        Returns:
            csr_matrix: Vectorized output
        """

        return self.vectorizer.predict(corpus, **kwargs)

    @staticmethod
    def load_data_from_file(
        data_path,
        label_text_path=None,
        split_sep="\t",
        maxsplit=-1,
        text_pos=1,
        label_pos=0,
        negative_sampling='tfn',
    ):
        """Parse a tab-separated text file to a CSR label matrix and a list of text strings.

        Text format for each line:
        <comma-separated label indices><TAB><space-separated text string>
        Example: l_1,..,l_k<TAB>w_1 w_2 ... w_t
            l_k is the zero-based index for the t-th relevant label
            w_t is the t-th token in the string

        Args:
            data_path (str): Path to the text file
            label_text_path (str, optional): Path to the label text file.
                The main purpose is to obtain the number of labels. Default: None
            split_sep (str, optional): The separator. Default: "\t".
            maxsplit (int, optional): The max number of splits for each line. Default: -1 to denote full split
            text_pos (int, optional): The position of the text part in each line. Default: 1.
            label_pos (int, optional): The position of the text part in each line. Default: 0.
        """
        if not os.path.isfile(data_path):
            raise FileNotFoundError(f"cannot find input text file at {data_path}")
        with open(data_path, "r", encoding="utf-8") as fin:
            label_strings, corpus = [], []
            for line in fin:
                parts = line.strip("\n")
                parts = parts.split(split_sep, maxsplit)
                if len(parts) < max(label_pos, text_pos) + 1:
                    raise ValueError(f"corrupted line from input text file:\n{line}")
                label_strings.append(parts[label_pos])
                text_string = parts[text_pos]
                corpus.append(text_string)

        def convert_label_to_Y(label_strings, L):
            rows, cols, vals = [], [], []
            for i, label in enumerate(label_strings):
                label_list =[x for x in  list(map(int, label.split(","))) if x >= 0]
                if len(label_list) == 0:
                    continue
                rows += [i] * len(label_list)
                cols += label_list
                vals += [1] * len(label_list)
            Y = smat.csr_matrix(
                (vals, (rows, cols)), shape=(len(label_strings), L), dtype=np.float32
            )
            return Y

        
        def convert_label_to_Y_and_M(label_strings, L):
              rows_Y, cols_Y, vals_Y = [], [], []
              rows_M, cols_M, vals_M = [], [], []
              for i, label in enumerate(label_strings):
                  label_Y_list = []
                  label_M_list = []
                  for x in list(map(int, label.split(","))):
                      if x >= 0:
                          label_Y_list.append(x)
                      else:
                          label_M_list.append(int((x+1)*-1))
                  if len(label_Y_list) >  0:
                      rows_Y += [i] * len(label_Y_list)
                      cols_Y += label_Y_list
                      vals_Y += [1] * len(label_Y_list)
                  if len(label_M_list) > 0:
                      rows_M += [i] * len(label_M_list)
                      cols_M += label_M_list
                      vals_M += [1] * len(label_M_list)
              Y = smat.csr_matrix(
                  (vals_Y, (rows_Y, cols_Y)), shape=(len(label_strings), L), dtype=np.float32
              )
              M = smat.csr_matrix(
                  (vals_M, (rows_M, cols_M)), shape=(len(label_strings), L), dtype=np.float32
                )
              return Y, M

        negative_sample_matrix = None
        label_matrix = None
        if label_text_path is not None:
            if not os.path.isfile(label_text_path):
                raise FileNotFoundError(f"cannot find label text file at: {label_text_path}")
            # this is used to obtain the total number of labels L to construct Y with a correct shape
            L = sum(1 for line in open(label_text_path, "r", encoding="utf-8") if line)
            if negative_sampling != "usn":
                label_matrix = convert_label_to_Y(label_strings, L)
            else:
                label_matrix, negative_sample_matrix = convert_label_to_Y_and_M(label_strings, L)
        if negative_sampling != "usn":
            return label_matrix, corpus
        return label_matrix, negative_sample_matrix, corpus

class BuildPreprocessorCommand(SubCommand):
    """Command to train a preprocessor"""

    @staticmethod
    def run(args):
        """Train a preprocessor.

        Args:
            args (argparse.Namespace): Command line argument parsed by `parser.parse_args()`
        """
        if not args.from_file:
            _, corpus = Preprocessor.load_data_from_file(
                args.input_text_path,
                maxsplit=args.maxsplit,
                text_pos=args.text_pos,
            )
        else:
            corpus = args.input_text_path
        vectorizer_config = Vectorizer.load_config_from_args(args)
        preprocessor = Preprocessor.train(corpus, vectorizer_config, dtype=args.dtype)
        preprocessor.save(args.output_model_folder)

    @classmethod
    def add_parser(cls, super_parser):
        """Add parser to the run.

        Args:
            super_parser (argparse.ArgumentParser): Argument parser.
        """
        parser = super_parser.add_parser("build", aliases=[], help="Build a preprocessor")
        cls.add_arguments(parser)
        parser.set_defaults(run=cls.run)

    @staticmethod
    def add_arguments(parser):
        """Add arguments for the build.

        Args:
            parser (argparse.ArgumentParser): Argument parser.
        """
        parser.add_argument(
            "-i", "--input-text-path", type=str, required=True, help="text input file name"
        )

        vectorizer_config_group_parser = parser.add_mutually_exclusive_group()
        vectorizer_config_group_parser.add_argument(
            "--vectorizer-config-path",
            type=str,
            default=None,
            metavar="VECTORIZER_CONFIG_PATH",
            help="Json file for vectorizer config (default tfidf vectorizer)",
        )

        vectorizer_config_group_parser.add_argument(
            "--vectorizer-config-json",
            type=str,
            default='{"type":"tfidf", "kwargs":{}}',
            metavar="VECTORIZER_CONFIG_JSON",
            help=f'Json-format string for vectorizer config (default {{"type":"tfidf", "kwargs":{{}}}}). Other type option: {list(vectorizer_dict.keys())}',
        )

        parser.add_argument(
            "-m", "--output-model-folder", type=str, required=True, help="model folder name"
        )

        parser.add_argument(
            "--maxsplit",
            type=int,
            default=-1,
            help="the max number of splits used to partition each line. (default -1 to denote full split)",
        )

        parser.add_argument(
            "--text-pos",
            type=int,
            default=1,
            help="the position of the text part in each line. (default 1)",
        )

        parser.add_argument(
            "-t",
            "--dtype",
            type=lambda x: np.float32 if "32" in x else np.float64,
            default=np.float32,
            help="data type for the output csr matrix. float32 | float64. (default float32)",
        )

        parser.add_argument(
            "--from-file",
            action="store_true",
            help="[Only support tfidf vectorizer] training without preloading corpus to memory. If true, --input-text-path is expected to be a file or a folder containing files that each line contains only input text.",
        )


class RunPreprocessorCommand(SubCommand):
    """Command to preprocess text using an existing preprocessor"""

    @staticmethod
    def run(args):
        """Preprocess text using an existing preprocessor.

        Args:
            args (argparse.Namespace): Command line argument parsed by `parser.parse_args()`
        """
        preprocessor = Preprocessor.load(args.input_preprocessor_folder)
        if args.from_file and not args.output_label_path:
            corpus = args.input_text_path
        else:
            Y, corpus = Preprocessor.load_data_from_file(
                args.input_text_path,
                label_text_path=args.label_text_path,
                maxsplit=args.maxsplit,
                text_pos=args.text_pos,
                label_pos=args.label_pos,
            )
        X = preprocessor.predict(
            corpus,
            batch_size=args.batch_size,
            use_gpu_if_available=not args.disable_gpu,
            buffer_size=args.buffer_size,
            threads=args.threads,
        )

        smat_util.save_matrix(args.output_inst_path, X)

        if args.output_label_path and Y is not None:
            smat_util.save_matrix(args.output_label_path, Y)

    @classmethod
    def add_parser(cls, super_parser):
        """Add parser to the run.

        Args:
            super_parser (argparse.ArgumentParser): Argument parser.
        """
        parser = super_parser.add_parser("run", aliases=[], help="Run a pre-built preprocessor")
        cls.add_arguments(parser)
        parser.set_defaults(run=cls.run)

    @staticmethod
    def add_arguments(parser):
        """Add arguments for the run.

        Args:
            parser (argparse.ArgumentParser): Argument parser.
        """
        parser.add_argument(
            "-p",
            "--input-preprocessor-folder",
            type=str,
            required=True,
            help="preprocessor folder name",
        )
        parser.add_argument(
            "-i", "--input-text-path", type=str, required=True, help="text input file name"
        )
        parser.add_argument(
            "-x",
            "--output-inst-path",
            type=str,
            required=True,
            help="output inst file name",
        )
        parser.add_argument(
            "--maxsplit",
            type=int,
            default=-1,
            help="the number of splits used to partition each line. (default -1 to denote full split))",
        )
        parser.add_argument(
            "--text-pos",
            type=int,
            default=1,
            help="the position of the text part in each line. (default 1)",
        )
        parser.add_argument(
            "-l", "--label-text-path", type=str, default=None, help="label text file name"
        )
        parser.add_argument(
            "-y", "--output-label-path", type=str, default=None, help="output label file name"
        )
        parser.add_argument(
            "--label-pos",
            type=int,
            default=0,
            help="the position of the text part in each line. (default 0)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=8,
            help="batch size for Transformer vectorizer embedding evaluation (default 8)",
        )
        parser.add_argument(
            "--disable-gpu",
            action="store_true",
            help="disable CUDA even if it's available",
        )
        parser.add_argument(
            "--threads",
            type=int,
            default=-1,
            help="number of threads to use for predict (default -1 to use all)",
        )
        parser.add_argument(
            "--from-file",
            action="store_true",
            help="[Only support tfidf vectorizer] predict without preloading corpus to memory. If true, --input-text-path is expected to be a file that each line contains only input text.",
        )
        parser.add_argument(
            "--buffer-size",
            type=int,
            default=0,
            help="number of bytes to use as file I/O buffer if --from-file (set to 0 to use default value)",
        )


def get_parser():
    """Get a parser for training preprocessor and preprocessing text"""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help="subcommands", metavar="SUBCOMMAND")
    subparsers.required = True
    BuildPreprocessorCommand.add_parser(subparsers)
    RunPreprocessorCommand.add_parser(subparsers)
    return parser


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    args.run(args)
