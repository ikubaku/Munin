import unittest
import result


class TestCodeSlice(unittest.TestCase):
    SOURCE_CODE = "#include <stdio.h>\n" \
                  "\n" \
                  "int main(void) {\n" \
                  "  printf(\"Hello, world!\\n\");\n" \
                  "  \n" \
                  "  return 0;\n" \
                  "}\n" \
                  "\n"

    def test_get_code_from(self):
        code_slice = result.CodeSlice(
            result.CodePosition(4, 3),
            result.CodePosition(6, 8),
        )
        res = code_slice.get_code_from(TestCodeSlice.SOURCE_CODE)
        self.assertEqual("printf(\"Hello, world!\\n\");\n"
                         "  \n"
                         "  return\n",
                         res)


if __name__ == '__main__':
    unittest.main()
