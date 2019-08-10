# set the main compiler here. Options e.g.: 'gcc', 'g++'
CC := g++
# directories
SRCDIR := .
BUILDDIR := build
TARGET := producer

SRCEXT := cpp
SOURCES := $(shell find $(SRCDIR) -type f -name *.$(SRCEXT))
OBJECTS := $(patsubst $(SRCDIR)/%,$(BUILDDIR)/%,$(SOURCES:.$(SRCEXT)=.o))

# use -ggdb for GNU debugger
# CFLAGS := -g -ggdb -gdwarf-2 -Wall -Wno-comment -std=c++11
CFLAGS := -O2 -Wall -Wno-comment -std=c++11

#LIB := -lm
INC := -Iinclude

#all: $(TARGET) $(TARGET)
all: $(TARGET)
	@echo " Doing nothing..."

$(TARGET): $(OBJECTS)
	@echo " Linking..."
	@echo " $(CC) $^ -o $(TARGET) $(LIB)"; $(CC) $^ -o $(TARGET) $(LIB)

$(BUILDDIR)/%.o: $(SRCDIR)/%.$(SRCEXT)
	@mkdir -p $(BUILDDIR)
	@echo " $(CC) $(CFLAGS) $(INC) -c -o $@ $<"; $(CC) $(CFLAGS) $(INC) -c -o $@ $<

clean:
	@echo " Cleaning..."; 
	$(RM) -r $(BUILDDIR) $(TARGET) *~

.PHONY: clean
