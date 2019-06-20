# set the main compiler here. Options e.g.: 'gcc', 'g++'
CC := arm-openwrt-linux-uclibcgnueabi-c++
# directories
SRCDIR := .
BUILDDIR := build
TARGET := echo-server

SRCEXT := cpp
SOURCES := $(shell find $(SRCDIR) -type f -name *.$(SRCEXT))
OBJECTS := $(patsubst $(SRCDIR)/%,$(BUILDDIR)/%,$(SOURCES:.$(SRCEXT)=.o))

# use -ggdb for GNU debugger
# CFLAGS := -g -ggdb -gdwarf-2 -Wall -Wno-comment -std=c++11
# CFLAGS := -O3 -Wall -Wno-comment -std=c++11

LIB := -lm
LD := arm-openwrt-linux-muslgnueabi-ld
INC := -I ~/workbench/openwrt/staging_dir/target-arm_arm1176jzf-s+vfp_uClibc-0.9.33.2_eabi/usr/include ~/workbench/openwrt/staging_dir/target-arm_arm1176jzf-s+vfp_uClibc-0.9.33.2_eabi/usr/lib

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
