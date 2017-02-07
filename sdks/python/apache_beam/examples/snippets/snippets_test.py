#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Tests for all code snippets used in public docs."""

import glob
import gzip
import logging
import os
import tempfile
import unittest
import uuid

import apache_beam as beam
from apache_beam import coders
from apache_beam import pvalue
from apache_beam import typehints
from apache_beam.transforms.util import assert_that
from apache_beam.transforms.util import equal_to
from apache_beam.utils.pipeline_options import TypeOptions
from apache_beam.examples.snippets import snippets

# pylint: disable=expression-not-assigned
from apache_beam.test_pipeline import TestPipeline


class ParDoTest(unittest.TestCase):
  """Tests for model/par-do."""

  def test_pardo(self):
    # Note: "words" and "ComputeWordLengthFn" are referenced by name in
    # the text of the doc.

    words = ['aa', 'bbb', 'c']

    # [START model_pardo_pardo]
    class ComputeWordLengthFn(beam.DoFn):
      def process(self, element):
        return [len(element)]
    # [END model_pardo_pardo]

    # [START model_pardo_apply]
    # Apply a ParDo to the PCollection "words" to compute lengths for each word.
    word_lengths = words | beam.ParDo(ComputeWordLengthFn())
    # [END model_pardo_apply]
    self.assertEqual({2, 3, 1}, set(word_lengths))

  def test_pardo_yield(self):
    words = ['aa', 'bbb', 'c']

    # [START model_pardo_yield]
    class ComputeWordLengthFn(beam.DoFn):
      def process(self, element):
        yield len(element)
    # [END model_pardo_yield]

    word_lengths = words | beam.ParDo(ComputeWordLengthFn())
    self.assertEqual({2, 3, 1}, set(word_lengths))

  def test_pardo_using_map(self):
    words = ['aa', 'bbb', 'c']
    # [START model_pardo_using_map]
    word_lengths = words | beam.Map(len)
    # [END model_pardo_using_map]

    self.assertEqual({2, 3, 1}, set(word_lengths))

  def test_pardo_using_flatmap(self):
    words = ['aa', 'bbb', 'c']
    # [START model_pardo_using_flatmap]
    word_lengths = words | beam.FlatMap(lambda word: [len(word)])
    # [END model_pardo_using_flatmap]

    self.assertEqual({2, 3, 1}, set(word_lengths))

  def test_pardo_using_flatmap_yield(self):
    words = ['aA', 'bbb', 'C']

    # [START model_pardo_using_flatmap_yield]
    def capitals(word):
      for letter in word:
        if 'A' <= letter <= 'Z':
          yield letter
    all_capitals = words | beam.FlatMap(capitals)
    # [END model_pardo_using_flatmap_yield]

    self.assertEqual({'A', 'C'}, set(all_capitals))

  def test_pardo_with_label(self):
    # pylint: disable=line-too-long
    words = ['aa', 'bbc', 'defg']
    # [START model_pardo_with_label]
    result = words | 'CountUniqueLetters' >> beam.Map(
        lambda word: len(set(word)))
    # [END model_pardo_with_label]

    self.assertEqual({1, 2, 4}, set(result))

  def test_pardo_side_input(self):
    p = TestPipeline()
    words = p | 'start' >> beam.Create(['a', 'bb', 'ccc', 'dddd'])

    # [START model_pardo_side_input]
    # Callable takes additional arguments.
    def filter_using_length(word, lower_bound, upper_bound=float('inf')):
      if lower_bound <= len(word) <= upper_bound:
        yield word

    # Construct a deferred side input.
    avg_word_len = (words
                    | beam.Map(len)
                    | beam.CombineGlobally(beam.combiners.MeanCombineFn()))

    # Call with explicit side inputs.
    small_words = words | 'small' >> beam.FlatMap(filter_using_length, 0, 3)

    # A single deferred side input.
    larger_than_average = (words | 'large' >> beam.FlatMap(
        filter_using_length,
        lower_bound=pvalue.AsSingleton(avg_word_len)))

    # Mix and match.
    small_but_nontrivial = words | beam.FlatMap(filter_using_length,
                                                lower_bound=2,
                                                upper_bound=pvalue.AsSingleton(
                                                    avg_word_len))
    # [END model_pardo_side_input]

    beam.assert_that(small_words, beam.equal_to(['a', 'bb', 'ccc']))
    beam.assert_that(larger_than_average, beam.equal_to(['ccc', 'dddd']),
                     label='larger_than_average')
    beam.assert_that(small_but_nontrivial, beam.equal_to(['bb']),
                     label='small_but_not_trivial')
    p.run()

  def test_pardo_side_input_dofn(self):
    words = ['a', 'bb', 'ccc', 'dddd']

    # [START model_pardo_side_input_dofn]
    class FilterUsingLength(beam.DoFn):
      def process(self, element, lower_bound, upper_bound=float('inf')):
        if lower_bound <= len(element) <= upper_bound:
          yield element

    small_words = words | beam.ParDo(FilterUsingLength(), 0, 3)
    # [END model_pardo_side_input_dofn]
    self.assertEqual({'a', 'bb', 'ccc'}, set(small_words))

  def test_pardo_with_side_outputs(self):
    # [START model_pardo_emitting_values_on_side_outputs]
    class ProcessWords(beam.DoFn):

      def process(self, element, cutoff_length, marker):
        if len(element) <= cutoff_length:
          # Emit this short word to the main output.
          yield element
        else:
          # Emit this word's long length to a side output.
          yield pvalue.SideOutputValue(
              'above_cutoff_lengths', len(element))
        if element.startswith(marker):
          # Emit this word to a different side output.
          yield pvalue.SideOutputValue('marked strings', element)
    # [END model_pardo_emitting_values_on_side_outputs]

    words = ['a', 'an', 'the', 'music', 'xyz']

    # [START model_pardo_with_side_outputs]
    results = (words | beam.ParDo(ProcessWords(), cutoff_length=2, marker='x')
               .with_outputs('above_cutoff_lengths', 'marked strings',
                             main='below_cutoff_strings'))
    below = results.below_cutoff_strings
    above = results.above_cutoff_lengths
    marked = results['marked strings']  # indexing works as well
    # [END model_pardo_with_side_outputs]

    self.assertEqual({'a', 'an'}, set(below))
    self.assertEqual({3, 5}, set(above))
    self.assertEqual({'xyz'}, set(marked))

    # [START model_pardo_with_side_outputs_iter]
    below, above, marked = (words
                            | beam.ParDo(
                                ProcessWords(), cutoff_length=2, marker='x')
                            .with_outputs('above_cutoff_lengths',
                                          'marked strings',
                                          main='below_cutoff_strings'))
    # [END model_pardo_with_side_outputs_iter]

    self.assertEqual({'a', 'an'}, set(below))
    self.assertEqual({3, 5}, set(above))
    self.assertEqual({'xyz'}, set(marked))

  def test_pardo_with_undeclared_side_outputs(self):
    numbers = [1, 2, 3, 4, 5, 10, 20]

    # [START model_pardo_with_side_outputs_undeclared]
    def even_odd(x):
      yield pvalue.SideOutputValue('odd' if x % 2 else 'even', x)
      if x % 10 == 0:
        yield x

    results = numbers | beam.FlatMap(even_odd).with_outputs()

    evens = results.even
    odds = results.odd
    tens = results[None]  # the undeclared main output
    # [END model_pardo_with_side_outputs_undeclared]

    self.assertEqual({2, 4, 10, 20}, set(evens))
    self.assertEqual({1, 3, 5}, set(odds))
    self.assertEqual({10, 20}, set(tens))


class TypeHintsTest(unittest.TestCase):

  def test_bad_types(self):
    p = TestPipeline()
    evens = None  # pylint: disable=unused-variable

    # [START type_hints_missing_define_numbers]
    numbers = p | beam.Create(['1', '2', '3'])
    # [END type_hints_missing_define_numbers]

    # Consider the following code.
    # pylint: disable=expression-not-assigned
    # pylint: disable=unused-variable
    # [START type_hints_missing_apply]
    evens = numbers | beam.Filter(lambda x: x % 2 == 0)
    # [END type_hints_missing_apply]

    # Now suppose numbers was defined as [snippet above].
    # When running this pipeline, you'd get a runtime error,
    # possibly on a remote machine, possibly very late.

    with self.assertRaises(TypeError):
      p.run()

    # To catch this early, we can assert what types we expect.
    with self.assertRaises(typehints.TypeCheckError):
      # [START type_hints_takes]
      p.options.view_as(TypeOptions).pipeline_type_check = True
      evens = numbers | beam.Filter(lambda x: x % 2 == 0).with_input_types(int)
      # [END type_hints_takes]

    # Type hints can be declared on DoFns and callables as well, rather
    # than where they're used, to be more self contained.
    with self.assertRaises(typehints.TypeCheckError):
      # [START type_hints_do_fn]
      @beam.typehints.with_input_types(int)
      class FilterEvensDoFn(beam.DoFn):
        def process(self, element):
          if element % 2 == 0:
            yield element
      evens = numbers | beam.ParDo(FilterEvensDoFn())
      # [END type_hints_do_fn]

    words = p | 'words' >> beam.Create(['a', 'bb', 'c'])
    # One can assert outputs and apply them to transforms as well.
    # Helps document the contract and checks it at pipeline construction time.
    # [START type_hints_transform]
    T = beam.typehints.TypeVariable('T')

    @beam.typehints.with_input_types(T)
    @beam.typehints.with_output_types(beam.typehints.Tuple[int, T])
    class MyTransform(beam.PTransform):
      def expand(self, pcoll):
        return pcoll | beam.Map(lambda x: (len(x), x))

    words_with_lens = words | MyTransform()
    # [END type_hints_transform]

    # pylint: disable=expression-not-assigned
    with self.assertRaises(typehints.TypeCheckError):
      words_with_lens | beam.Map(lambda x: x).with_input_types(
          beam.typehints.Tuple[int, int])

  def test_runtime_checks_off(self):
    # pylint: disable=expression-not-assigned
    p = TestPipeline()
    # [START type_hints_runtime_off]
    p | beam.Create(['a']) | beam.Map(lambda x: 3).with_output_types(str)
    p.run()
    # [END type_hints_runtime_off]

  def test_runtime_checks_on(self):
    # pylint: disable=expression-not-assigned
    p = TestPipeline()
    with self.assertRaises(typehints.TypeCheckError):
      # [START type_hints_runtime_on]
      p.options.view_as(TypeOptions).runtime_type_check = True
      p | beam.Create(['a']) | beam.Map(lambda x: 3).with_output_types(str)
      p.run()
      # [END type_hints_runtime_on]

  def test_deterministic_key(self):
    p = TestPipeline()
    lines = (p | beam.Create(
        ['banana,fruit,3', 'kiwi,fruit,2', 'kiwi,fruit,2', 'zucchini,veg,3']))

    # [START type_hints_deterministic_key]
    class Player(object):
      def __init__(self, team, name):
        self.team = team
        self.name = name

    class PlayerCoder(beam.coders.Coder):
      def encode(self, player):
        return '%s:%s' % (player.team, player.name)

      def decode(self, s):
        return Player(*s.split(':'))

      def is_deterministic(self):
        return True

    beam.coders.registry.register_coder(Player, PlayerCoder)

    def parse_player_and_score(csv):
      name, team, score = csv.split(',')
      return Player(team, name), int(score)

    totals = (
        lines
        | beam.Map(parse_player_and_score)
        | beam.CombinePerKey(sum).with_input_types(
            beam.typehints.Tuple[Player, int]))
    # [END type_hints_deterministic_key]

    assert_that(
        totals | beam.Map(lambda (k, v): (k.name, v)),
        equal_to([('banana', 3), ('kiwi', 4), ('zucchini', 3)]))

    p.run()


class SnippetsTest(unittest.TestCase):
  # Replacing text read/write transforms with dummy transforms for testing.
  class DummyReadTransform(beam.PTransform):
    """A transform that will replace iobase.ReadFromText.

    To be used for testing.
    """

    def __init__(self, file_to_read=None, compression_type=None):
      self.file_to_read = file_to_read
      self.compression_type = compression_type

    class ReadDoFn(beam.DoFn):

      def __init__(self, file_to_read, compression_type):
        self.file_to_read = file_to_read
        self.compression_type = compression_type
        self.coder = coders.StrUtf8Coder()

      def process(self, element):
        pass

      def finish_bundle(self):
        assert self.file_to_read
        for file_name in glob.glob(self.file_to_read):
          if self.compression_type is None:
            with open(file_name) as file:
              for record in file:
                yield self.coder.decode(record.rstrip('\n'))
          else:
            with gzip.open(file_name, 'r') as file:
              for record in file:
                yield self.coder.decode(record.rstrip('\n'))

    def expand(self, pcoll):
      return pcoll | beam.Create([None]) | 'DummyReadForTesting' >> beam.ParDo(
          SnippetsTest.DummyReadTransform.ReadDoFn(
              self.file_to_read, self.compression_type))

  class DummyWriteTransform(beam.PTransform):
    """A transform that will replace iobase.WriteToText.

    To be used for testing.
    """

    def __init__(self, file_to_write=None, file_name_suffix=''):
      self.file_to_write = file_to_write

    class WriteDoFn(beam.DoFn):
      def __init__(self, file_to_write):
        self.file_to_write = file_to_write
        self.file_obj = None
        self.coder = coders.ToStringCoder()

      def start_bundle(self):
        assert self.file_to_write
        self.file_to_write += str(uuid.uuid4())
        self.file_obj = open(self.file_to_write, 'w')

      def process(self, element):
        assert self.file_obj
        self.file_obj.write(self.coder.encode(element) + '\n')

      def finish_bundle(self):
        assert self.file_obj
        self.file_obj.close()

    def expand(self, pcoll):
      return pcoll | 'DummyWriteForTesting' >> beam.ParDo(
          SnippetsTest.DummyWriteTransform.WriteDoFn(self.file_to_write))

  def setUp(self):
    self.old_read_from_text = beam.io.ReadFromText
    self.old_write_to_text = beam.io.WriteToText

    # Monkey patching to allow testing pipelines defined in snippets.py using
    # real data.
    beam.io.ReadFromText = SnippetsTest.DummyReadTransform
    beam.io.WriteToText = SnippetsTest.DummyWriteTransform

  def tearDown(self):
    beam.io.ReadFromText = self.old_read_from_text
    beam.io.WriteToText = self.old_write_to_text

  def create_temp_file(self, contents=''):
    with tempfile.NamedTemporaryFile(delete=False) as f:
      f.write(contents)
      return f.name

  def get_output(self, path, sorted_output=True, suffix=''):
    all_lines = []
    for file_name in glob.glob(path + '*'):
      with open(file_name) as f:
        lines = f.readlines()
        all_lines.extend([s.rstrip('\n') for s in lines])

    if sorted_output:
      return sorted(s.rstrip('\n') for s in all_lines)
    else:
      return all_lines

  def test_model_pipelines(self):
    temp_path = self.create_temp_file('aa bb cc\n bb cc\n cc')
    result_path = temp_path + '.result'
    snippets.model_pipelines([
        '--input=%s*' % temp_path,
        '--output=%s' % result_path])
    self.assertEqual(
        self.get_output(result_path),
        [str(s) for s in [(u'aa', 1), (u'bb', 2), (u'cc', 3)]])

  def test_model_pcollection(self):
    temp_path = self.create_temp_file()
    snippets.model_pcollection(['--output=%s' % temp_path])
    self.assertEqual(self.get_output(temp_path, sorted_output=False), [
        'To be, or not to be: that is the question: ',
        'Whether \'tis nobler in the mind to suffer ',
        'The slings and arrows of outrageous fortune, ',
        'Or to take arms against a sea of troubles, '])

  def test_construct_pipeline(self):
    temp_path = self.create_temp_file(
        'abc def ghi\n jkl mno pqr\n stu vwx yz')
    result_path = self.create_temp_file()
    snippets.construct_pipeline({'read': temp_path, 'write': result_path})
    self.assertEqual(
        self.get_output(result_path),
        ['cba', 'fed', 'ihg', 'lkj', 'onm', 'rqp', 'uts', 'xwv', 'zy'])

  def test_model_custom_source(self):
    snippets.model_custom_source(100)

  def test_model_custom_sink(self):
    tempdir_name = tempfile.mkdtemp()

    class SimpleKV(object):

      def __init__(self, tmp_dir):
        self._dummy_token = 'dummy_token'
        self._tmp_dir = tmp_dir

      def connect(self, url):
        return self._dummy_token

      def open_table(self, access_token, table_name):
        assert access_token == self._dummy_token
        file_name = self._tmp_dir + os.sep + table_name
        assert not os.path.exists(file_name)
        open(file_name, 'wb').close()
        return table_name

      def write_to_table(self, access_token, table_name, key, value):
        assert access_token == self._dummy_token
        file_name = self._tmp_dir + os.sep + table_name
        assert os.path.exists(file_name)
        with open(file_name, 'ab') as f:
          f.write(key + ':' + value + os.linesep)

      def rename_table(self, access_token, old_name, new_name):
        assert access_token == self._dummy_token
        old_file_name = self._tmp_dir + os.sep + old_name
        new_file_name = self._tmp_dir + os.sep + new_name
        assert os.path.isfile(old_file_name)
        assert not os.path.exists(new_file_name)

        os.rename(old_file_name, new_file_name)

    snippets.model_custom_sink(
        SimpleKV(tempdir_name),
        [('key' + str(i), 'value' + str(i)) for i in range(100)],
        'final_table_no_ptransform', 'final_table_with_ptransform')

    expected_output = [
        'key' + str(i) + ':' + 'value' + str(i) for i in range(100)]

    glob_pattern = tempdir_name + os.sep + 'final_table_no_ptransform*'
    output_files = glob.glob(glob_pattern)
    assert output_files

    received_output = []
    for file_name in output_files:
      with open(file_name) as f:
        for line in f:
          received_output.append(line.rstrip(os.linesep))

    self.assertItemsEqual(expected_output, received_output)

    glob_pattern = tempdir_name + os.sep + 'final_table_with_ptransform*'
    output_files = glob.glob(glob_pattern)
    assert output_files

    received_output = []
    for file_name in output_files:
      with open(file_name) as f:
        for line in f:
          received_output.append(line.rstrip(os.linesep))

    self.assertItemsEqual(expected_output, received_output)

  def test_model_textio(self):
    temp_path = self.create_temp_file('aa bb cc\n bb cc\n cc')
    result_path = temp_path + '.result'
    snippets.model_textio({'read': temp_path, 'write': result_path})
    self.assertEqual(
        ['aa', 'bb', 'bb', 'cc', 'cc', 'cc'],
        self.get_output(result_path, suffix='.csv'))

  def test_model_textio_compressed(self):
    temp_path = self.create_temp_file('aa\nbb\ncc')
    gzip_file_name = temp_path + '.gz'
    with open(temp_path) as src, gzip.open(gzip_file_name, 'wb') as dst:
      dst.writelines(src)
    snippets.model_textio_compressed(
        {'read': gzip_file_name}, ['aa', 'bb', 'cc'])

  def test_model_datastoreio(self):
    # We cannot test datastoreio functionality in unit tests therefore we limit
    # ourselves to making sure the pipeline containing Datastore read and write
    # transforms can be built.
    # TODO(vikasrk): Expore using Datastore Emulator.
    snippets.model_datastoreio()

  def test_model_bigqueryio(self):
    # We cannot test BigQueryIO functionality in unit tests therefore we limit
    # ourselves to making sure the pipeline containing BigQuery sources and
    # sinks can be built.
    snippets.model_bigqueryio()

  def _run_test_pipeline_for_options(self, fn):
    temp_path = self.create_temp_file('aa\nbb\ncc')
    result_path = temp_path + '.result'
    fn([
        '--input=%s*' % temp_path,
        '--output=%s' % result_path])
    self.assertEqual(
        ['aa', 'bb', 'cc'],
        self.get_output(result_path))

  def test_pipeline_options_local(self):
    self._run_test_pipeline_for_options(snippets.pipeline_options_local)

  def test_pipeline_options_remote(self):
    self._run_test_pipeline_for_options(snippets.pipeline_options_remote)

  def test_pipeline_options_command_line(self):
    self._run_test_pipeline_for_options(snippets.pipeline_options_command_line)

  def test_pipeline_logging(self):
    result_path = self.create_temp_file()
    lines = ['we found love right where we are',
             'we found love right from the start',
             'we found love in a hopeless place']
    snippets.pipeline_logging(lines, result_path)
    self.assertEqual(
        sorted(' '.join(lines).split(' ')),
        self.get_output(result_path))

  def test_examples_wordcount(self):
    pipelines = [snippets.examples_wordcount_minimal,
                 snippets.examples_wordcount_wordcount,
                 snippets.pipeline_monitoring]

    for pipeline in pipelines:
      temp_path = self.create_temp_file(
          'abc def ghi\n abc jkl')
      result_path = self.create_temp_file()
      pipeline({'read': temp_path, 'write': result_path})
      self.assertEqual(
          self.get_output(result_path),
          ['abc: 2', 'def: 1', 'ghi: 1', 'jkl: 1'])

  def test_examples_wordcount_debugging(self):
    temp_path = self.create_temp_file(
        'Flourish Flourish Flourish stomach abc def')
    result_path = self.create_temp_file()
    snippets.examples_wordcount_debugging(
        {'read': temp_path, 'write': result_path})
    self.assertEqual(
        self.get_output(result_path),
        ['Flourish: 3', 'stomach: 1'])

  def test_model_composite_transform_example(self):
    contents = ['aa bb cc', 'bb cc', 'cc']
    result_path = self.create_temp_file()
    snippets.model_composite_transform_example(contents, result_path)
    self.assertEqual(['aa: 1', 'bb: 2', 'cc: 3'], self.get_output(result_path))

  def test_model_multiple_pcollections_flatten(self):
    contents = ['a', 'b', 'c', 'd', 'e', 'f']
    result_path = self.create_temp_file()
    snippets.model_multiple_pcollections_flatten(contents, result_path)
    self.assertEqual(contents, self.get_output(result_path))

  def test_model_multiple_pcollections_partition(self):
    contents = [17, 42, 64, 32, 0, 99, 53, 89]
    result_path = self.create_temp_file()
    snippets.model_multiple_pcollections_partition(contents, result_path)
    self.assertEqual(['0', '17', '32', '42', '53', '64', '89', '99'],
                     self.get_output(result_path))

  def test_model_group_by_key(self):
    contents = ['a bb ccc bb bb a']
    result_path = self.create_temp_file()
    snippets.model_group_by_key(contents, result_path)
    expected = [('a', 2), ('bb', 3), ('ccc', 1)]
    self.assertEqual([str(s) for s in expected], self.get_output(result_path))

  def test_model_co_group_by_key_tuple(self):
    email_list = [['a', 'a@example.com'], ['b', 'b@example.com']]
    phone_list = [['a', 'x4312'], ['b', 'x8452']]
    result_path = self.create_temp_file()
    snippets.model_co_group_by_key_tuple(email_list, phone_list, result_path)
    expect = ['a; a@example.com; x4312', 'b; b@example.com; x8452']
    self.assertEqual(expect, self.get_output(result_path))

  def test_model_join_using_side_inputs(self):
    name_list = ['a', 'b']
    email_list = [['a', 'a@example.com'], ['b', 'b@example.com']]
    phone_list = [['a', 'x4312'], ['b', 'x8452']]
    result_path = self.create_temp_file()
    snippets.model_join_using_side_inputs(
        name_list, email_list, phone_list, result_path)
    expect = ['a; a@example.com; x4312', 'b; b@example.com; x8452']
    self.assertEqual(expect, self.get_output(result_path))


class CombineTest(unittest.TestCase):
  """Tests for model/combine."""

  def test_global_sum(self):
    pc = [1, 2, 3]
    # [START global_sum]
    result = pc | beam.CombineGlobally(sum)
    # [END global_sum]
    self.assertEqual([6], result)

  def test_combine_values(self):
    occurences = [('cat', 1), ('cat', 5), ('cat', 9), ('dog', 5), ('dog', 2)]
    # [START combine_values]
    first_occurences = occurences | beam.GroupByKey() | beam.CombineValues(min)
    # [END combine_values]
    self.assertEqual({('cat', 1), ('dog', 2)}, set(first_occurences))

  def test_combine_per_key(self):
    player_accuracies = [
        ('cat', 1), ('cat', 5), ('cat', 9), ('cat', 1),
        ('dog', 5), ('dog', 2)]
    # [START combine_per_key]
    avg_accuracy_per_player = (player_accuracies
                               | beam.CombinePerKey(
                                   beam.combiners.MeanCombineFn()))
    # [END combine_per_key]
    self.assertEqual({('cat', 4.0), ('dog', 3.5)}, set(avg_accuracy_per_player))

  def test_combine_concat(self):
    pc = ['a', 'b']

    # [START combine_concat]
    def concat(values, separator=', '):
      return separator.join(values)
    with_commas = pc | beam.CombineGlobally(concat)
    with_dashes = pc | beam.CombineGlobally(concat, separator='-')
    # [END combine_concat]
    self.assertEqual(1, len(with_commas))
    self.assertTrue(with_commas[0] in {'a, b', 'b, a'})
    self.assertEqual(1, len(with_dashes))
    self.assertTrue(with_dashes[0] in {'a-b', 'b-a'})

  def test_bounded_sum(self):
    # [START combine_bounded_sum]
    pc = [1, 10, 100, 1000]

    def bounded_sum(values, bound=500):
      return min(sum(values), bound)
    small_sum = pc | beam.CombineGlobally(bounded_sum)              # [500]
    large_sum = pc | beam.CombineGlobally(bounded_sum, bound=5000)  # [1111]
    # [END combine_bounded_sum]
    self.assertEqual([500], small_sum)
    self.assertEqual([1111], large_sum)

  def test_combine_reduce(self):
    factors = [2, 3, 5, 7]
    # [START combine_reduce]
    import functools
    import operator
    product = factors | beam.CombineGlobally(
        functools.partial(reduce, operator.mul), 1)
    # [END combine_reduce]
    self.assertEqual([210], product)

  def test_custom_average(self):
    pc = [2, 3, 5, 7]

    # [START combine_custom_average]
    class AverageFn(beam.CombineFn):
      def create_accumulator(self):
        return (0.0, 0)

      def add_input(self, (sum, count), input):
        return sum + input, count + 1

      def merge_accumulators(self, accumulators):
        sums, counts = zip(*accumulators)
        return sum(sums), sum(counts)

      def extract_output(self, (sum, count)):
        return sum / count if count else float('NaN')
    average = pc | beam.CombineGlobally(AverageFn())
    # [END combine_custom_average]
    self.assertEqual([4.25], average)

  def test_keys(self):
    occurrences = [('cat', 1), ('cat', 5), ('dog', 5), ('cat', 9), ('dog', 2)]
    unique_keys = occurrences | snippets.Keys()
    self.assertEqual({'cat', 'dog'}, set(unique_keys))

  def test_count(self):
    occurrences = ['cat', 'dog', 'cat', 'cat', 'dog']
    perkey_counts = occurrences | snippets.Count()
    self.assertEqual({('cat', 3), ('dog', 2)}, set(perkey_counts))


if __name__ == '__main__':
  logging.getLogger().setLevel(logging.INFO)
  unittest.main()